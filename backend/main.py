"""API Baixar Vídeos — downloads com yt-dlp (Railway)."""
from __future__ import annotations

import ipaddress
import logging
import mimetypes
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from yt_dlp.utils import DownloadError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("baixarvideos")
app = FastAPI(title="Baixar Vídeos API", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://baixarvideos.vercel.app",
        "https://baixarvideos-segadair-boop.vercel.app",
        "https://baixarvideos-git-main-segadair-boop.vercel.app",
    ],
    allow_origin_regex=r"^https://baixarvideos(?:-[a-z0-9-]+)?\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

ALLOWED_HOSTS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com", "instagram.com",
    "tiktok.com", "facebook.com", "fb.watch", "x.com", "twitter.com",
    "threads.net", "threads.com", "vimeo.com", "twitch.tv",
    "reddit.com", "dailymotion.com", "soundcloud.com", "pinterest.com",
    "pin.it", "streamable.com",
)
FORMATS = {
    "video_360": "bv*[height<=360]+ba/b[height<=360]/best[height<=360]/best",
    "video_480": "bv*[height<=480]+ba/b[height<=480]/best[height<=480]/best",
    "video_720": "bv*[height<=720]+ba/b[height<=720]/best[height<=720]/best",
    "video_1080": "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]/best",
    "audio_mp3": "bestaudio/best",
}
MAX_FILE_BYTES = 350 * 1024 * 1024
MAX_DURATION_SECONDS = 3600
JOB_TTL_SECONDS = 1800
RATE_WINDOW_SECONDS = 3600
RATE_LIMIT = 8
MAX_ACTIVE_JOBS = 2
DOWNLOAD_ROOT = Path(os.getenv("DOWNLOAD_ROOT", "/tmp/baixarvideos"))
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, dict] = {}
_rate: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.RLock()
_pool = ThreadPoolExecutor(max_workers=MAX_ACTIVE_JOBS, thread_name_prefix="video-job")


class LinkRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)


class DownloadRequest(LinkRequest):
    quality: str = Field(default="video_720", max_length=24)


def validated_url(value: str) -> str:
    value = value.strip()
    if len(value) > 2048 or any(ch.isspace() for ch in value):
        raise HTTPException(400, detail="Cole um link válido, sem espaços.")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError()
        if host == "localhost" or host.startswith("xn--"):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
            raise ValueError()
        except ValueError:
            if any(host == item or host.endswith("." + item) for item in ALLOWED_HOSTS):
                return value
    except (ValueError, TypeError):
        pass
    raise HTTPException(400, detail="Plataforma não suportada. Use um endereço HTTPS de YouTube, Instagram, TikTok ou outra plataforma listada.")


def ydl_opts() -> dict:
    return {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "socket_timeout": 25, "retries": 2, "fragment_retries": 2,
        "skip_unavailable_fragments": False, "cachedir": False,
        "nocheckcertificate": False, "playlistend": 1,
        "max_filesize": MAX_FILE_BYTES, "extractor_retries": 2,
    }


def extract_metadata(url: str) -> dict:
    with yt_dlp.YoutubeDL({**ydl_opts(), "skip_download": True}) as engine:
        item = engine.extract_info(url, download=False)
    if not isinstance(item, dict):
        raise ValueError("Vídeo não encontrado.")
    if item.get("_type") == "playlist":
        item = next((x for x in (item.get("entries") or []) if x), None)
    if not item:
        raise ValueError("Vídeo não encontrado.")
    duration = item.get("duration") or 0
    if duration and duration > MAX_DURATION_SECONDS:
        raise ValueError("A duração máxima é de 60 minutos.")
    return {
        "title": str(item.get("title") or "Vídeo sem título")[:180],
        "uploader": str(item.get("uploader") or item.get("channel") or "")[:100],
        "duration": int(duration),
        "thumbnail": item.get("thumbnail") if str(item.get("thumbnail") or "").startswith("https://") else None,
        "extractor": str(item.get("extractor_key") or "")[:60],
        "choices": [
            {"value": "video_360", "label": "Vídeo 360p"},
            {"value": "video_480", "label": "Vídeo 480p"},
            {"value": "video_720", "label": "Vídeo até 720p (recomendado)"},
            {"value": "video_1080", "label": "Vídeo até 1080p"},
            {"value": "audio_mp3", "label": "Somente áudio MP3"},
        ],
    }


def set_job(job_id: str, **changes) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes)


def snapshot(job: dict) -> dict:
    return {
        "id": job["id"], "status": job["status"],
        "progress": job.get("progress", 0), "error": job.get("error"),
        "filename": job.get("filename"),
        "download_url": "/api/jobs/" + job["id"] + "/file" if job["status"] == "done" else None,
    }


def cleanup_expired() -> None:
    now = time.time()
    expired_paths = []
    with _lock:
        for job_id, job in list(_jobs.items()):
            if job["status"] in ("queued", "running"):
                continue
            if now - job.get("finished_at", now) > JOB_TTL_SECONDS:
                expired_paths.append(job.get("directory"))
                del _jobs[job_id]
        for remote_ip, values in list(_rate.items()):
            while values and now - values[0] > RATE_WINDOW_SECONDS:
                values.popleft()
            if not values:
                del _rate[remote_ip]
    for folder in expired_paths:
        if folder:
            shutil.rmtree(folder, ignore_errors=True)


def run_download(job_id: str, url: str, quality: str, folder: Path) -> None:
    set_job(job_id, status="running")
    try:
        def progress_hook(event: dict) -> None:
            if event.get("status") != "downloading":
                return
            current = int(event.get("downloaded_bytes") or 0)
            total = int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0)
            if current > MAX_FILE_BYTES:
                raise DownloadError("Arquivo excede 350 MB.")
            set_job(job_id, progress=max(0, min(98, round(100 * current / total))) if total else 0)

        opts = {
            **ydl_opts(), "format": FORMATS[quality],
            "outtmpl": str(folder / "%(title).90s.%(id)s.%(ext)s"),
            "restrictfilenames": True, "progress_hooks": [progress_hook],
            "merge_output_format": "mp4", "overwrites": False,
        }
        if quality == "audio_mp3":
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        with yt_dlp.YoutubeDL(opts) as engine:
            info = engine.extract_info(url, download=True)
        if not isinstance(info, dict):
            raise RuntimeError("A plataforma não retornou um vídeo.")
        if info.get("duration") and info["duration"] > MAX_DURATION_SECONDS:
            raise RuntimeError("O vídeo excede 60 minutos.")

        candidates = sorted(
            (p for p in folder.iterdir() if p.is_file()
             and p.suffix.lower() not in {".part", ".ytdl", ".json"}
             and not p.name.endswith(".temp")),
            key=lambda p: p.stat().st_size, reverse=True,
        )
        if not candidates:
            raise RuntimeError("Arquivo de vídeo não encontrado após a conversão.")
        video_file = candidates[0]
        if video_file.stat().st_size > MAX_FILE_BYTES:
            raise RuntimeError("O arquivo excede 350 MB.")
        set_job(
            job_id, status="done", progress=100, filename=video_file.name,
            path=str(video_file), finished_at=time.time(),
        )
        logger.info("Download completed: %s", job_id)
    except Exception as exc:
        logger.warning("Download failed %s: %s", job_id, type(exc).__name__)
        message = str(exc).strip() or "Não foi possível baixar o vídeo."
        message = message.splitlines()[-1][:320]
        if "HTTP Error 429" in message:
            message = "A plataforma limitou as tentativas. Tente mais tarde."
        elif "Sign in to confirm" in message or "cookies" in message.lower():
            message = "Este vídeo exige autenticação ou verificação da plataforma."
        elif "/tmp/" in message:
            message = "Falha durante o processamento. Tente outra qualidade."
        set_job(job_id, status="error", error=message, finished_at=time.time())
        shutil.rmtree(folder, ignore_errors=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "baixarvideos", "yt_dlp": yt_dlp.version.__version__, "ffmpeg": bool(shutil.which("ffmpeg"))}


@app.post("/api/info")
async def info(payload: LinkRequest) -> dict:
    import asyncio
    url = validated_url(payload.url)
    try:
        return await asyncio.wait_for(asyncio.to_thread(extract_metadata, url), timeout=55)
    except TimeoutError:
        raise HTTPException(504, detail="A plataforma demorou para responder. Tente novamente.")
    except Exception as exc:
        logger.info("Metadata lookup failed: %s", type(exc).__name__)
        raise HTTPException(422, detail="Não foi possível acessar esse vídeo. Pode ser privado, protegido ou exigir autenticação.")


@app.post("/api/jobs", status_code=202)
async def create_job(payload: DownloadRequest, request: Request) -> dict:
    url = validated_url(payload.url)
    if payload.quality not in FORMATS:
        raise HTTPException(400, detail="Qualidade não reconhecida.")
    cleanup_expired()
    remote_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    with _lock:
        now = time.time()
        values = _rate[remote_ip]
        while values and now - values[0] > RATE_WINDOW_SECONDS:
            values.popleft()
        if len(values) >= RATE_LIMIT:
            raise HTTPException(429, detail="Limite de 8 downloads por hora atingido para esta conexão.")
        if sum(job["status"] in ("queued", "running") for job in _jobs.values()) >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, detail="Servidor ocupado. Tente novamente em alguns instantes.")
        job_id = secrets.token_urlsafe(22)
        folder = Path(tempfile.mkdtemp(prefix="download-", dir=DOWNLOAD_ROOT))
        _jobs[job_id] = {
            "id": job_id, "status": "queued", "progress": 0,
            "created_at": now, "directory": str(folder), "error": None,
        }
        values.append(now)
    _pool.submit(run_download, job_id, url, payload.quality, folder)
    return snapshot(_jobs[job_id])


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    cleanup_expired()
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, detail="Download expirado ou não encontrado.")
        return snapshot(job)


@app.get("/api/jobs/{job_id}/file")
async def download_file(job_id: str):
    cleanup_expired()
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["status"] != "done":
            raise HTTPException(404, detail="Arquivo ainda não está disponível.")
        filename, path = job["filename"], job["path"]
    if not Path(path).is_file():
        raise HTTPException(410, detail="O arquivo expirou. Solicite novamente.")
    return FileResponse(
        path, media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        filename=filename,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


# Modo Vercel: processamento + entrega no mesmo request. Funções stateless
# não podem guardar tarefas em memória entre requests diferentes.
@app.get("/api/download")
async def download_once(request: Request, url: str, quality: str = "video_720"):
    import asyncio
    from starlette.background import BackgroundTask
    target = validated_url(url)
    if quality not in FORMATS:
        raise HTTPException(400, detail="Qualidade inválida.")
    cleanup_expired()

    # Não confiar em cabeçalhos X-Forwarded-For fornecidos diretamente pelo cliente.
    client_ip = request.client.host if request.client else "unknown"
    with _lock:
        now = time.time()
        counts = _rate[client_ip]
        while counts and now - counts[0] > RATE_WINDOW_SECONDS:
            counts.popleft()
        if len(counts) >= RATE_LIMIT:
            raise HTTPException(429, detail="Limite de tentativas atingido para esta conexão.")
        counts.append(now)

    folder = Path(tempfile.mkdtemp(prefix="vercel-download-", dir=DOWNLOAD_ROOT))

    def prepare_download():
        opts = {
            **ydl_opts(), "format": FORMATS[quality],
            "outtmpl": str(folder / "%(title).90s.%(id)s.%(ext)s"),
            "restrictfilenames": True,
            "merge_output_format": "mp4",
            "overwrites": False,
        }
        if quality == "audio_mp3":
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        with yt_dlp.YoutubeDL(opts) as engine:
            data = engine.extract_info(target, download=True)
        if not isinstance(data, dict):
            raise RuntimeError("Vídeo indisponível.")
        duration = data.get("duration") or 0
        if duration > MAX_DURATION_SECONDS:
            raise RuntimeError("A duração ultrapassa 60 minutos.")
        files = sorted(
            (p for p in folder.iterdir() if p.is_file()
             and p.suffix.lower() not in {".part", ".ytdl", ".json"}),
            key=lambda p: p.stat().st_size, reverse=True,
        )
        if not files:
            raise RuntimeError("O processamento não gerou um arquivo.")
        if files[0].stat().st_size > MAX_FILE_BYTES:
            raise RuntimeError("Arquivo maior que o limite de 350 MB.")
        return files[0]

    try:
        # Vercel (plano Hobby): normalmente até 300 segundos por invocação.
        file = await asyncio.wait_for(asyncio.to_thread(prepare_download), timeout=240)
    except TimeoutError:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(504, detail="O download demorou demais. Tente menor qualidade.")
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        logger.warning("Download on Vercel failed: %s", type(exc).__name__)
        message = str(exc).splitlines()[-1][:220] if str(exc) else "Não foi possível baixar o vídeo."
        if "Sign in to confirm" in message or "cookies" in message.lower():
            message = "A plataforma exige login ou verificação; este vídeo não pode ser baixado automaticamente."
        if "/tmp/" in message:
            message = "A plataforma não conseguiu processar este arquivo."
        raise HTTPException(422, detail=message)

    # FileResponse é streaming, não serializa um vídeo inteiro em JSON.
    return FileResponse(
        path=file,
        filename=file.name,
        media_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(shutil.rmtree, folder, ignore_errors=True),
    )
