"""Guarda o refresh token do YouTube criptografado no repositório (igual ao do TikTok).
A chave vem do YT_CLIENT_SECRET, que fica só nos Secrets do GitHub."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

import config

ARQUIVO = config.PASTA / "youtube.token"


def _cifra() -> Fernet:
    if not config.YT_CLIENT_SECRET:
        raise RuntimeError("Falta o segredo YT_CLIENT_SECRET.")
    chave = hashlib.sha256(("autovideo-yt:" + config.YT_CLIENT_SECRET).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def salvar(refresh_token: str):
    ARQUIVO.write_bytes(_cifra().encrypt(refresh_token.encode()))


def carregar() -> str:
    if ARQUIVO.exists():
        try:
            return _cifra().decrypt(ARQUIVO.read_bytes()).decode()
        except InvalidToken:
            raise RuntimeError("youtube.token não abre com o YT_CLIENT_SECRET atual. Conecte o YouTube de novo.")
    return config.YT_REFRESH_TOKEN


def conectado() -> bool:
    return bool(config.YT_CLIENT_ID and config.YT_CLIENT_SECRET and (ARQUIVO.exists() or config.YT_REFRESH_TOKEN))
