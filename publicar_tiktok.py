"""Envia o vídeo para o TikTok pela Content Posting API (grátis)."""
import math
import os
import time

import requests

import config

API = "https://open.tiktokapis.com/v2"
ARQUIVO_TOKEN = config.PASTA / ".tiktok_refresh_token"


def _refresh_token_atual() -> str:
    # Se uma execução anterior recebeu um refresh token novo, ele fica salvo aqui.
    if ARQUIVO_TOKEN.exists():
        return ARQUIVO_TOKEN.read_text().strip()
    return config.TIKTOK_REFRESH_TOKEN


def _access_token() -> str:
    refresh = _refresh_token_atual()
    if not (config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET and refresh):
        raise RuntimeError("Faltam TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET ou TIKTOK_REFRESH_TOKEN (rode autorizar_tiktok.py).")
    r = requests.post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config.TIKTOK_CLIENT_KEY,
            "client_secret": config.TIKTOK_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        },
        timeout=30,
    )
    dados = r.json()
    if "access_token" not in dados:
        raise RuntimeError(f"TikTok recusou o refresh token: {dados}")
    novo = dados.get("refresh_token")
    if novo and novo != refresh:
        ARQUIVO_TOKEN.write_text(novo)
        if os.getenv("GITHUB_ACTIONS"):
            print("   ⚠️  O TikTok trocou o refresh token. Atualize o segredo TIKTOK_REFRESH_TOKEN no GitHub.")
    return dados["access_token"]


def _checar(r: requests.Response) -> dict:
    dados = r.json()
    erro = dados.get("error", {})
    if r.status_code != 200 or erro.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: {r.status_code} {erro.get('code')} - {erro.get('message')}")
    return dados.get("data", {})


def _plano_de_pedacos(tamanho: int):
    """Regras do TikTok: pedaços de 5 a 64 MB; arquivo até 64 MB vai inteiro."""
    if tamanho <= 64 * 1024 * 1024:
        return tamanho, 1
    pedaco = 10 * 1024 * 1024
    return pedaco, tamanho // pedaco  # o último pedaço leva a sobra


def publicar(arquivo, roteiro: dict) -> str:
    token = _access_token()
    cab = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    tamanho = os.path.getsize(arquivo)
    pedaco, qtd = _plano_de_pedacos(tamanho)
    origem = {"source": "FILE_UPLOAD", "video_size": tamanho, "chunk_size": pedaco, "total_chunk_count": qtd}

    legenda = f"{roteiro['titulo']}\n\n{roteiro.get('descricao', '')}\n\n{' '.join(roteiro.get('hashtags', []))}"

    if config.TIKTOK_MODO == "direto":
        info = _checar(requests.post(f"{API}/post/publish/creator_info/query/", headers=cab, timeout=30))
        opcoes = info.get("privacy_level_options", [])
        privacidade = config.TIKTOK_PRIVACIDADE if config.TIKTOK_PRIVACIDADE in opcoes else "SELF_ONLY"
        corpo = {
            "post_info": {
                "title": legenda[:2200],
                "privacy_level": privacidade,
                "disable_duet": False,
                "disable_stitch": False,
                "disable_comment": False,
                "video_cover_timestamp_ms": 1000,
                "is_aigc": config.TIKTOK_ROTULO_IA,
            },
            "source_info": origem,
        }
        url_init = f"{API}/post/publish/video/init/"
    else:
        # Modo rascunho: vai para a caixa de entrada do app; legenda você cola lá.
        corpo = {"source_info": origem}
        url_init = f"{API}/post/publish/inbox/video/init/"

    dados = _checar(requests.post(url_init, headers=cab, json=corpo, timeout=30))
    publish_id, upload_url = dados["publish_id"], dados["upload_url"]

    with open(arquivo, "rb") as f:
        for i in range(qtd):
            inicio = i * pedaco
            fim = tamanho - 1 if i == qtd - 1 else inicio + pedaco - 1
            f.seek(inicio)
            bloco = f.read(fim - inicio + 1)
            r = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(bloco)),
                    "Content-Range": f"bytes {inicio}-{fim}/{tamanho}",
                },
                data=bloco,
                timeout=300,
            )
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"Upload no TikTok falhou: {r.status_code} {r.text[:300]}")
            print(f"   TikTok: pedaço {i + 1}/{qtd} enviado")

    # acompanha o processamento
    for _ in range(30):
        time.sleep(10)
        st = _checar(requests.post(f"{API}/post/publish/status/fetch/", headers=cab,
                                   json={"publish_id": publish_id}, timeout=30))
        estado = st.get("status")
        if estado in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if estado == "FAILED":
            raise RuntimeError(f"TikTok recusou o vídeo: {st.get('fail_reason')}")

    if config.TIKTOK_MODO == "direto":
        return f"publicado (id {publish_id}, privacidade {corpo['post_info']['privacy_level']})"
    return "enviado para a caixa de entrada do app TikTok: abra o app e toque em Publicar"
