# AutoVídeo 🎬

Gera sozinho vídeos curtos (Shorts/TikTok) e publica no YouTube e no TikTok, de graça.

```
tema → roteiro (Gemini) → narração (Edge-TTS) → clipes (Pexels) → vídeo 9:16 com legendas (FFmpeg) → YouTube + TikTok
```

Tudo roda no plano gratuito: Gemini, Edge-TTS, Pexels, YouTube Data API, TikTok API e GitHub Actions.

---

## 1. Testar no seu computador (10 minutos)

1. Instale o **Python 3.10+** e o **FFmpeg**
   - Windows: `winget install Python.Python.3.12` e `winget install Gyan.FFmpeg`
   - Mac: `brew install python ffmpeg`
2. Na pasta do projeto:
   ```
   pip install -r requirements.txt
   ```
3. Copie `.env.exemplo` para `.env` e preencha só estas duas (ambas grátis):
   - `GEMINI_API_KEY` → https://aistudio.google.com/apikey
   - `PEXELS_API_KEY` → https://www.pexels.com/api/ (crie conta e clique em "Your API Key")
4. Gere um vídeo sem publicar:
   ```
   python main.py --sem-publicar
   ```
   O vídeo aparece em `saida/`. Sem as chaves ele usa um roteiro de exemplo e fundos animados.

**Personalizar:** troque `NICHO` e `VOZ` no `.env`. Vozes em português: `pt-BR-AntonioNeural`,
`pt-BR-FranciscaNeural`, `pt-BR-ThalitaNeural`. Coloque músicas sem direitos autorais (ex.: Biblioteca
de Áudio do YouTube) em `musica/` e uma delas toca baixinho no fundo. Em `temas.txt` você deixa uma fila
de assuntos (um por linha); quando acabar, a IA escolhe sozinha sem repetir.

---

## 2. Conectar o YouTube

1. Acesse https://console.cloud.google.com → crie um projeto.
2. **APIs e serviços → Biblioteca** → ative **YouTube Data API v3**.
3. **Tela de consentimento OAuth** → tipo *Externo* → preencha nome e e-mail → adicione o escopo
   `.../auth/youtube.upload` → em *Usuários de teste* adicione o seu Gmail.
4. ⚠️ Depois, na mesma tela, clique em **Publicar app** (status "Em produção").
   Se ficar em "Teste", o acesso expira a cada 7 dias e a automação para.
   Vai aparecer um aviso de "app não verificado" na hora de autorizar: clique em *Avançado → Acessar*. É o seu próprio app.
5. **Credenciais → Criar credenciais → ID do cliente OAuth → App para computador** → baixe o JSON,
   renomeie para `client_secret.json` e coloque na pasta do projeto.
6. Rode `python autorizar_youtube.py`, faça login com a conta do canal e copie as 3 linhas para o `.env`.

**Importante:** projetos novos da API só conseguem enviar vídeos **privados**. Para publicar público
automaticamente, peça a auditoria gratuita no formulário "YouTube API Services - Audit and Quota Extension".
Até lá, o vídeo sobe privado e você só muda para público no YouTube Studio (1 clique).
A cota grátis dá para uns 6 uploads por dia.

---

## 3. Conectar o TikTok

1. Acesse https://developers.tiktok.com → crie uma conta de desenvolvedor → **Manage apps → Connect an app**.
2. Adicione os produtos **Login Kit** e **Content Posting API** (ative "Direct Post" se quiser o modo direto).
3. Escopos: `user.info.basic`, `video.upload`, `video.publish`.
4. Em Login Kit → *Redirect URI*, coloque uma URL **https** sua. Serve até uma página do GitHub Pages
   (ex.: `https://seuusuario.github.io/`). Ela não precisa fazer nada, só existir.
   O TikTok pede também URLs de Termos de Uso e Política de Privacidade: podem ser páginas simples no mesmo GitHub Pages.
5. Envie o app para revisão (pode levar alguns dias). Enquanto isso, no modo *Sandbox*, adicione sua conta como usuária de teste.
6. Preencha `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` e `TIKTOK_REDIRECT_URI` no `.env`,
   rode `python autorizar_tiktok.py` e siga as instruções.

**Os dois modos (`TIKTOK_MODO`):**
- `rascunho` (padrão) → o vídeo chega na caixa de entrada do app TikTok e você toca em **Publicar**.
  Sai público normalmente, mesmo sem auditoria. Recomendado para começar.
- `direto` → publica 100% sozinho, mas sem a auditoria do TikTok o post fica visível só pra você,
  e a conta precisa estar no modo privado. Depois de aprovado na auditoria, pode publicar público.

O vídeo é marcado como "gerado por IA" no TikTok e como mídia sintética no YouTube, como as duas plataformas pedem.

---

## 4. Rodar sozinho todo dia (GitHub Actions, grátis)

1. Crie um repositório no GitHub e envie esta pasta (o `.gitignore` já impede o envio do `.env` e dos segredos).
2. No repositório: **Settings → Secrets and variables → Actions**
   - *Secrets* (uma por linha do seu `.env`): `GEMINI_API_KEY`, `PEXELS_API_KEY`, `YT_CLIENT_ID`,
     `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`
   - *Variables* (opcionais): `NICHO`, `VOZ`, `YT_PRIVACIDADE`, `TIKTOK_MODO`, `PUBLICAR_YOUTUBE`, `PUBLICAR_TIKTOK`
3. Pronto: todo dia às 11h47 (Brasília) sai um vídeo novo. Para testar na hora: aba **Actions → Vídeo diário → Run workflow**.
   O vídeo também fica disponível para download na própria execução por 7 dias.

Para mudar o horário ou fazer 2 vídeos por dia, edite a linha `cron` em `.github/workflows/diario.yml`.

---

## Dicas para o canal crescer (e não perder monetização)

- O YouTube não monetiza conteúdo "produzido em massa e repetitivo". Varie formatos, revise roteiros
  de vez em quando e não publique dezenas por dia: 1 a 2 vídeos diários é o ideal.
- Confira os fatos dos primeiros vídeos: a IA às vezes erra.
- Clipes do Pexels e vozes do Edge-TTS podem ser usados em vídeos, mas para música use só faixas livres.

## Estrutura

| Arquivo | O que faz |
|---|---|
| `main.py` | Roda tudo em sequência |
| `config.py` | Configurações (nicho, voz, privacidade...) |
| `roteiro.py` | Escreve o roteiro com o Gemini |
| `voz.py` | Gera a narração e os tempos de cada palavra |
| `video.py` | Baixa clipes, cria legendas e monta o MP4 |
| `publicar_youtube.py` / `publicar_tiktok.py` | Fazem o upload |
| `autorizar_*.py` | Rodam uma vez para conectar suas contas |
