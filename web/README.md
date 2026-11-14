# Interface web — Baixar Vídeos

Esta pasta contém uma interface estática em português para visualização na **Vercel**.

## Status funcional

- Validação de URL, identificação de plataformas, histórico local, tema claro/escuro, visualização para celular e desktop.
- Arquivos com URL direta terminando em MP4, WebM, MOV, MP3 e formatos comuns podem ser abertos diretamente no navegador. A opção de salvar depende do servidor de origem e das regras do navegador.
- Links de YouTube, Instagram, TikTok e outras plataformas **não são baixados ou convertidos na Vercel nesta versão**. A interface oferece o comando para usar o Yoinks original no terminal do computador.
- O código de terminal em ../src continua preservado.

## Publicar pela Vercel

1. Importe o GitHub segadair-boop/baixarvideos na Vercel.
2. Configure **Root Directory** como web.
3. Escolha **Framework Preset: Other** (sem framework).
4. Não é necessário comando de build; publique os arquivos estáticos da pasta web.
5. Configure o branch de produção como main. Os pushes no GitHub criarão novas visualizações.

## Por que não executar yt-dlp na Vercel?

A aplicação original utiliza processos de sistema, download de executáveis e arquivos de vídeo potencialmente grandes, o que não se adapta automaticamente às funções com limites de duração, armazenamento temporário e transferência de dados da Vercel. Para downloads completos pelo navegador, será necessário um serviço backend próprio, com limites, segurança de URLs, monitoramento e conformidade de uso.

## Uso responsável

Baixe apenas conteúdos próprios ou para os quais você tenha autorização. Projeto baseado no [Yoinks](https://github.com/pablostanley/yoinks), licença MIT.
