"""Guarda o refresh token do TikTok criptografado dentro do repositório.

Assim a conexão pode ser feita pelo navegador (sem instalar nada) e o token,
que o TikTok troca de vez em quando, se atualiza sozinho a cada execução.
A chave de criptografia vem do TIKTOK_CLIENT_SECRET, que fica só nos Secrets.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

import config

ARQUIVO = config.PASTA / "tiktok.token"


def _cifra() -> Fernet:
    if not config.TIKTOK_CLIENT_SECRET:
        raise RuntimeError("Falta o segredo TIKTOK_CLIENT_SECRET.")
    chave = hashlib.sha256(("autovideo:" + config.TIKTOK_CLIENT_SECRET).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def salvar(refresh_token: str):
    ARQUIVO.write_bytes(_cifra().encrypt(refresh_token.encode()))


def carregar() -> str:
    """Token salvo no repositório; se não houver, usa o segredo TIKTOK_REFRESH_TOKEN."""
    if ARQUIVO.exists():
        try:
            return _cifra().decrypt(ARQUIVO.read_bytes()).decode()
        except InvalidToken:
            raise RuntimeError("tiktok.token não abre com o TIKTOK_CLIENT_SECRET atual. Conecte o TikTok de novo.")
    return config.TIKTOK_REFRESH_TOKEN


def conectado() -> bool:
    return bool(config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET and (ARQUIVO.exists() or config.TIKTOK_REFRESH_TOKEN))
