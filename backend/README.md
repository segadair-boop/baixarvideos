# Backend Baixar Vídeos — Railway

GitHub é a fonte do código; Vercel hospeda a interface estática em web/; Railway executa Python, yt-dlp e FFmpeg pelo Dockerfile na raiz.

Endpoints:
- GET /api/health: status do serviço.
- POST /api/info: JSON {"url":"https://www.youtube.com/watch?v=..."}.
- POST /api/jobs: JSON {"url":"...","quality":"video_720"}; retorno 202 com id.
- GET /api/jobs/{id}: andamento e erros.
- GET /api/jobs/{id}/file: arquivo final com Content-Disposition por até 30 minutos.

Permite somente links HTTPS das plataformas listadas. Limita arquivos a 350 MB, vídeos a 60 minutos, duas tarefas simultâneas, e oito por IP/hora. Armazenamento efêmero. Downloads privados, protegidos por DRM, exigindo login, cookies ou bloqueados pelos provedores podem falhar. Para acesso público em escala, adicione autenticação, quota persistente e antifraude.

Publicação: Railway identifica automaticamente o Dockerfile na raiz; gere um domínio Railway e configure-o em web/config.js. Testes: python -m unittest discover -s backend -p 'test_*.py'. Download permitido somente para conteúdo próprio ou autorizado.
