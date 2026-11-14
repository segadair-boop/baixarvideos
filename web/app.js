(() => {
  'use strict';

  const HISTORY_KEY = 'baixarvideos:history:v1';
  const THEME_KEY = 'baixarvideos:theme:v1';
  const MAX_HISTORY = 6;
  const form = document.getElementById('video-form');
  const input = document.getElementById('video-url');
  const validation = document.getElementById('validation');
  const pasteButton = document.getElementById('paste-button');
  const result = document.getElementById('result');
  const resultTitle = document.getElementById('result-title');
  const resultSubtitle = document.getElementById('result-subtitle');
  const resultUrl = document.getElementById('result-url');
  const resultPrimary = document.getElementById('result-primary');
  const resultSecondary = document.getElementById('result-secondary');
  const resultNote = document.getElementById('result-note');
  const historyList = document.getElementById('history-list');
  const historyEmpty = document.getElementById('history-empty');
  const clearHistoryButton = document.getElementById('clear-history');
  const themeToggle = document.getElementById('theme-toggle');
  const themeSymbol = document.getElementById('theme-symbol');
  const toast = document.getElementById('toast');
  let activeLink = null;
  let toastTimer;

  const platforms = [
    { name: 'YouTube', hosts: ['youtube.com', 'youtu.be'] },
    { name: 'Instagram', hosts: ['instagram.com'] },
    { name: 'TikTok', hosts: ['tiktok.com'] },
    { name: 'Facebook', hosts: ['facebook.com', 'fb.watch'] },
    { name: 'X / Twitter', hosts: ['x.com', 'twitter.com'] },
    { name: 'Threads', hosts: ['threads.net', 'threads.com'] },
    { name: 'Vimeo', hosts: ['vimeo.com'] },
    { name: 'Twitch', hosts: ['twitch.tv'] },
    { name: 'Reddit', hosts: ['reddit.com'] }
  ];
  const mediaExtension = /\.(mp4|m4v|mov|webm|mkv|ogv|ogg|mp3|m4a|wav|aac|flac)$/i;

  function notify(message) {
    toast.textContent = message;
    toast.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add('hidden'), 3200);
  }

  function setMessage(message, error) {
    validation.textContent = message;
    validation.classList.toggle('error', Boolean(error));
  }

  function parseLink(value) {
    const trimmed = value.trim();
    if (!trimmed || trimmed.length > 4096 || /\s/.test(trimmed)) {
      throw new Error('Cole um link completo, sem espaços.');
    }
    let url;
    try { url = new URL(trimmed); }
    catch { throw new Error('Link inválido. Confira o endereço informado.'); }
    if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password) {
      throw new Error('Informe um endereço HTTP ou HTTPS válido.');
    }
    return url;
  }

  function matchHost(host, domain) {
    return host === domain || host.endsWith('.' + domain);
  }

  function classify(url) {
    const host = url.hostname.toLowerCase();
    const platform = platforms.find(p => p.hosts.some(h => matchHost(host, h)));
    const direct = mediaExtension.test(url.pathname);
    return { name: platform ? platform.name : host, direct: direct };
  }

  function commandFor(url) {
    return 'npx yoinks ' + JSON.stringify(url);
  }

  async function copyText(text) {
    if (!navigator.clipboard || !window.isSecureContext) {
      notify('Cópia automática indisponível. Selecione o texto manualmente.');
      return false;
    }
    try {
      await navigator.clipboard.writeText(text);
      notify('Copiado para a área de transferência.');
      return true;
    } catch {
      notify('O navegador bloqueou a cópia. Verifique as permissões.');
      return false;
    }
  }

  function storeHistory(url) {
    try {
      const previous = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      const valid = Array.isArray(previous) ? previous.filter(item => typeof item === 'string') : [];
      const updated = [url, ...valid.filter(item => item !== url)].slice(0, MAX_HISTORY);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    } catch { /* Private browsing / storage disabled */ }
    renderHistory();
  }

  function readHistory() {
    try {
      const data = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      return Array.isArray(data) ? data.filter(value => typeof value === 'string').slice(0, MAX_HISTORY) : [];
    } catch { return []; }
  }

  function renderHistory() {
    const items = readHistory();
    historyList.replaceChildren();
    historyEmpty.classList.toggle('hidden', items.length > 0);
    clearHistoryButton.disabled = items.length === 0;
    for (const value of items) {
      let host;
      try { host = new URL(value).hostname; } catch { continue; }
      const li = document.createElement('li');
      const icon = document.createElement('span');
      icon.className = 'overview-icon';
      icon.textContent = '↗';
      const detail = document.createElement('div');
      detail.className = 'history-meta';
      const domain = document.createElement('div');
      domain.className = 'history-domain';
      domain.textContent = host;
      const urlEl = document.createElement('div');
      urlEl.className = 'history-url';
      urlEl.textContent = value;
      detail.append(domain, urlEl);
      const use = document.createElement('button');
      use.type = 'button';
      use.textContent = 'Usar link';
      use.addEventListener('click', () => {
        input.value = value;
        form.requestSubmit();
        document.getElementById('baixar').scrollIntoView({ behavior: 'smooth' });
      });
      li.append(icon, detail, use);
      historyList.appendChild(li);
    }
  }

  function updateResult(url, classification) {
    activeLink = url.href;
    result.classList.remove('hidden');
    resultTitle.textContent = classification.direct ? 'Arquivo de mídia identificado' : 'Link de plataforma identificado';
    resultSubtitle.textContent = classification.direct ? 'Formato original disponível no endereço' : classification.name + ' · uso pelo Yoinks no computador';
    resultUrl.textContent = url.href;
    resultUrl.title = url.href;
    resultSecondary.href = url.href;
    if (classification.direct) {
      resultPrimary.textContent = 'Abrir / baixar mídia ↗';
      resultNote.textContent = 'O arquivo será aberto diretamente no servidor de origem. Dependendo do navegador e das permissões do site, use o menu do vídeo para salvar; a Vercel não armazena nem converte o arquivo.';
      resultPrimary.onclick = () => {
        const link = document.createElement('a');
        link.href = activeLink;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.download = decodeURIComponent(url.pathname.split('/').pop() || 'midia');
        document.body.appendChild(link);
        link.click();
        link.remove();
      };
    } else {
      resultPrimary.textContent = 'Copiar comando Yoinks';
      resultNote.textContent = 'O comando copiado deve ser executado no terminal do computador com Node.js 18+. Nesta versão web ainda não é possível extrair ou converter vídeos de plataformas na Vercel.';
      resultPrimary.onclick = () => { void copyText(commandFor(activeLink)); };
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      const url = parseLink(input.value);
      const classification = classify(url);
      setMessage('Link válido: ' + classification.name, false);
      updateResult(url, classification);
      storeHistory(url.href);
    } catch (error) {
      activeLink = null;
      result.classList.add('hidden');
      setMessage(error.message || 'Não foi possível validar o link.', true);
      input.focus();
    }
  });

  input.addEventListener('input', () => {
    result.classList.add('hidden');
    activeLink = null;
    setMessage('Use um endereço completo começando com https://', false);
  });

  pasteButton.addEventListener('click', async () => {
    if (!navigator.clipboard || !window.isSecureContext) {
      notify('Colagem automática indisponível. Cole manualmente no campo.');
      input.focus();
      return;
    }
    try {
      const value = await navigator.clipboard.readText();
      input.value = value.trim();
      input.focus();
      setMessage('Link colado. Clique em Verificar link.', false);
    } catch {
      notify('Permissão de área de transferência negada. Cole manualmente.');
      input.focus();
    }
  });

  clearHistoryButton.addEventListener('click', () => {
    try { localStorage.removeItem(HISTORY_KEY); }
    catch { /* Ignore disabled storage */ }
    renderHistory();
    notify('Histórico local limpo.');
  });

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeSymbol.textContent = theme === 'light' ? '☾' : '☀';
    themeToggle.setAttribute('aria-label', theme === 'light' ? 'Ativar tema escuro' : 'Ativar tema claro');
  }

  let initialTheme = 'dark';
  try { initialTheme = localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'; }
  catch { /* Default dark */ }
  applyTheme(initialTheme);
  themeToggle.addEventListener('click', () => {
    const updated = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(updated);
    try { localStorage.setItem(THEME_KEY, updated); } catch { /* No storage */ }
  });

  renderHistory();
})();