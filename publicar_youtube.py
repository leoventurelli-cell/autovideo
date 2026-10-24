"""Envia o vídeo para o YouTube pela YouTube Data API v3 (grátis, com cota diária)."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]


def _credenciais() -> Credentials:
    if not (config.YT_CLIENT_ID and config.YT_CLIENT_SECRET and config.YT_REFRESH_TOKEN):
        raise RuntimeError("Faltam YT_CLIENT_ID, YT_CLIENT_SECRET ou YT_REFRESH_TOKEN (rode autorizar_youtube.py).")
    cred = Credentials(
        token=None,
        refresh_token=config.YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YT_CLIENT_ID,
        client_secret=config.YT_CLIENT_SECRET,
        scopes=ESCOPOS,
    )
    cred.refresh(Request())
    return cred


def publicar(arquivo, roteiro: dict) -> str:
    youtube = build("youtube", "v3", credentials=_credenciais(), cache_discovery=False)

    hashtags = " ".join(roteiro.get("hashtags", []))
    if "#shorts" not in hashtags.lower():
        hashtags += " #shorts"
    corpo = {
        "snippet": {
            "title": roteiro["titulo"][:100],
            "description": f"{roteiro.get('descricao', '')}\n\n{hashtags}".strip()[:4900],
            "tags": [h.lstrip("#") for h in roteiro.get("hashtags", [])][:15],
            "categoryId": config.YT_CATEGORIA,
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": config.YT_PRIVACIDADE,
            "selfDeclaredMadeForKids": False,
            # Voz e roteiro são sintéticos: o YouTube pede essa declaração
            # para conteúdo realista alterado/gerado por IA.
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(str(arquivo), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    pedido = youtube.videos().insert(part="snippet,status", body=corpo, media_body=media)

    resposta = None
    while resposta is None:
        status, resposta = pedido.next_chunk()
        if status:
            print(f"   YouTube: {int(status.progress() * 100)}%")
    video_id = resposta["id"]
    privacidade = resposta.get("status", {}).get("privacyStatus")
    if privacidade == "private" and config.YT_PRIVACIDADE != "private":
        print("   ⚠️  O YouTube deixou o vídeo PRIVADO: seu projeto ainda não passou na auditoria da API.")
    return f"https://youtube.com/shorts/{video_id}"
