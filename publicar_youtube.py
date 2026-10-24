"""Envia o vídeo para o YouTube pela YouTube Data API v3 (grátis, com cota diária).
curto → publica como Short;  longo → vídeo normal com capítulos e capa (thumbnail)."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config
import youtube_token

ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]


def _credenciais() -> Credentials:
    refresh = youtube_token.carregar()
    if not (config.YT_CLIENT_ID and config.YT_CLIENT_SECRET and refresh):
        raise RuntimeError("YouTube não conectado: use o botão 'Conectar YouTube' no painel.")
    cred = Credentials(
        token=None,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YT_CLIENT_ID,
        client_secret=config.YT_CLIENT_SECRET,
        scopes=ESCOPOS,
    )
    cred.refresh(Request())
    return cred


def _tempo(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def descricao(roteiro: dict, formato: str, capitulos: list[tuple[float, str]] | None = None) -> str:
    hashtags = list(roteiro.get("hashtags", []))
    if formato == "curto" and "#shorts" not in [h.lower() for h in hashtags]:
        hashtags.append("#shorts")
    texto = roteiro.get("descricao", "").strip()
    if capitulos and len(capitulos) >= 3:
        # o YouTube cria capítulos se a lista começa em 0:00 e tem 3+ itens
        texto += "\n\n📌 Capítulos\n" + "\n".join(
            f"{_tempo(0 if i == 0 else t)} {titulo}" for i, (t, titulo) in enumerate(capitulos))
    texto += "\n\n" + " ".join(hashtags)
    return texto.strip()[:4900]


def publicar(arquivo, roteiro: dict, formato: str = "curto", capitulos=None, capa=None) -> str:
    youtube = build("youtube", "v3", credentials=_credenciais(), cache_discovery=False)

    corpo = {
        "snippet": {
            "title": roteiro["titulo"][:100],
            "description": descricao(roteiro, formato, capitulos),
            "tags": (roteiro.get("tags_youtube") or [h.lstrip("#") for h in roteiro.get("hashtags", [])])[:15],
            "categoryId": config.YT_CATEGORIA,
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": config.YT_PRIVACIDADE,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # declara conteúdo gerado por IA
        },
    }

    def enviar(c):
        media = MediaFileUpload(str(arquivo), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
        pedido = youtube.videos().insert(part="snippet,status", body=c, media_body=media)
        resposta = None
        while resposta is None:
            status, resposta = pedido.next_chunk()
            if status:
                print(f"   YouTube: {int(status.progress() * 100)}%")
        return resposta

    try:
        resposta = enviar(corpo)
    except HttpError as e:
        if "containsSyntheticMedia" in str(e):
            corpo["status"].pop("containsSyntheticMedia")
            resposta = enviar(corpo)
        else:
            raise

    video_id = resposta["id"]
    if capa:
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(capa), mimetype="image/jpeg")).execute()
            print("   YouTube: capa enviada")
        except HttpError as e:
            print(f"::warning title=YouTube::Capa não enviada (verifique o canal por telefone em youtube.com/verify): {e}")

    privacidade = resposta.get("status", {}).get("privacyStatus")
    if privacidade == "private" and config.YT_PRIVACIDADE != "private":
        print("::warning title=YouTube::O YouTube deixou o vídeo PRIVADO: o projeto ainda não passou na auditoria da API.")
    url = f"https://youtube.com/shorts/{video_id}" if formato == "curto" else f"https://youtu.be/{video_id}"
    print(f"::notice title=YouTube::{url} ({privacidade})")
    return url
