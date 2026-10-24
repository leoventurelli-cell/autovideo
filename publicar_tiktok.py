"""Envia o vídeo para o TikTok pela Content Posting API (grátis).

Modo "direto": publica sozinho com título, descrição e hashtags da IA.
Se o app ainda não passou na auditoria do TikTok e a conta é pública,
o TikTok recusa o post direto; aí o vídeo vai para a caixa de entrada
do app (você só toca em Publicar e cola a legenda copiada do painel).
"""
import os
import time

import requests

import config
import tiktok_token

API = "https://open.tiktokapis.com/v2"


def _access_token() -> str:
    refresh = tiktok_token.carregar()
    if not (config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET and refresh):
        raise RuntimeError("TikTok não conectado: use o botão 'Conectar TikTok' no painel.")
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
        raise RuntimeError(f"TikTok recusou a conexão (conecte de novo pelo painel): {dados.get('error_description') or dados}")
    # o TikTok pode devolver um refresh token novo: guarda para a próxima vez
    tiktok_token.salvar(dados.get("refresh_token") or refresh)
    return dados["access_token"]


class ErroTikTok(RuntimeError):
    def __init__(self, codigo, mensagem):
        super().__init__(f"TikTok: {codigo} - {mensagem}")
        self.codigo = codigo


def _checar(r: requests.Response) -> dict:
    dados = r.json()
    erro = dados.get("error", {})
    if r.status_code != 200 or erro.get("code") not in (None, "ok"):
        raise ErroTikTok(erro.get("code") or r.status_code, erro.get("message"))
    return dados.get("data", {})


def _plano_de_pedacos(tamanho: int):
    """Regras do TikTok: pedaços de 5 a 64 MB; arquivo até 64 MB vai inteiro."""
    if tamanho <= 64 * 1024 * 1024:
        return tamanho, 1
    pedaco = 10 * 1024 * 1024
    return pedaco, tamanho // pedaco  # o último pedaço leva a sobra


def legenda(roteiro: dict) -> str:
    hashtags = " ".join(roteiro.get("hashtags", []))
    return f"{roteiro['titulo']}\n\n{roteiro.get('descricao', '')}\n\n{hashtags}".strip()[:2200]


def _iniciar(cab, arquivo, roteiro, direto: bool):
    tamanho = os.path.getsize(arquivo)
    pedaco, qtd = _plano_de_pedacos(tamanho)
    origem = {"source": "FILE_UPLOAD", "video_size": tamanho, "chunk_size": pedaco, "total_chunk_count": qtd}
    if not direto:
        dados = _checar(requests.post(f"{API}/post/publish/inbox/video/init/", headers=cab,
                                      json={"source_info": origem}, timeout=30))
        return dados, tamanho, pedaco, qtd, None

    info = _checar(requests.post(f"{API}/post/publish/creator_info/query/", headers=cab, timeout=30))
    opcoes = info.get("privacy_level_options", [])
    privacidade = config.TIKTOK_PRIVACIDADE if config.TIKTOK_PRIVACIDADE in opcoes else (opcoes[0] if opcoes else "SELF_ONLY")
    corpo = {
        "post_info": {
            "title": legenda(roteiro),
            "privacy_level": privacidade,
            "disable_duet": False,
            "disable_stitch": False,
            "disable_comment": False,
            "video_cover_timestamp_ms": 1000,
            "is_aigc": config.TIKTOK_ROTULO_IA,
        },
        "source_info": origem,
    }
    dados = _checar(requests.post(f"{API}/post/publish/video/init/", headers=cab, json=corpo, timeout=30))
    return dados, tamanho, pedaco, qtd, privacidade


def publicar(arquivo, roteiro: dict) -> str:
    cab = {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json; charset=UTF-8"}

    direto = config.TIKTOK_MODO == "direto"
    try:
        dados, tamanho, pedaco, qtd, privacidade = _iniciar(cab, arquivo, roteiro, direto)
    except ErroTikTok as e:
        if not direto or e.codigo not in (
            "unaudited_client_can_only_post_to_private_accounts", "scope_not_authorized", "access_token_invalid_scope",
        ):
            raise
        print(f"::warning title=TikTok::Post direto ainda não liberado ({e.codigo}). Enviando para a caixa de entrada do app.")
        direto = False
        dados, tamanho, pedaco, qtd, privacidade = _iniciar(cab, arquivo, roteiro, False)

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

    estado, st = None, {}
    for _ in range(36):  # acompanha o processamento (até 6 minutos)
        time.sleep(10)
        st = _checar(requests.post(f"{API}/post/publish/status/fetch/", headers=cab,
                                   json={"publish_id": publish_id}, timeout=30))
        estado = st.get("status")
        print(f"   TikTok: status {estado}")
        if estado in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if estado == "FAILED":
            motivo = st.get("fail_reason")
            print(f"::error title=TikTok recusou o vídeo::{motivo} (publish_id {publish_id})")
            raise RuntimeError(f"TikTok recusou o vídeo: {motivo}")
    else:
        print(f"::error title=TikTok não confirmou::último status: {estado} (publish_id {publish_id}) {st}")
        raise RuntimeError(f"TikTok não confirmou o recebimento (último status: {estado})")
    print(f"::notice title=TikTok::{estado} (publish_id {publish_id})")

    if direto:
        visibilidade = "público" if privacidade == "PUBLIC_TO_EVERYONE" else f"visibilidade {privacidade}"
        return f"publicado direto com título e descrição ({visibilidade})"
    return "na caixa de entrada do app TikTok: toque em Publicar e cole a legenda copiada do painel"
