"""Envia para as redes um vídeo que JÁ está no painel (botões "Enviar no YouTube" / "Enviar em ambos").

Uso:  python enviar.py --id video-20261024-1748-8 --redes youtube,tiktok
"""
import argparse
import json
import re
import tempfile
import traceback
from pathlib import Path

import requests

import config

PAINEL = config.PASTA / "docs" / "videos.json"


def _id_de(v: dict) -> str:
    if v.get("id"):
        return v["id"]
    m = re.search(r"/download/([^/]+)/", v.get("mp4", ""))
    return m.group(1) if m else ""


def _baixar(url: str, destino: Path) -> Path:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for pedaco in r.iter_content(1 << 20):
                f.write(pedaco)
    return destino


def _roteiro(v: dict, videos: list[dict]) -> dict:
    t = v.get("textos") or {}
    legenda = v.get("legenda", "")
    hashtags_tt = (t.get("hashtags_tiktok") or " ".join(re.findall(r"#[^\s#]+", legenda))).split()
    desc = t.get("descricao_youtube") or legenda
    if v.get("formato") != "longo" and "#shorts" not in desc.lower():
        desc += " #shorts"
    if v.get("chamada_de"):  # Short de chamada: põe o link do vídeo longo
        longo = next((x for x in videos if _id_de(x) == v["chamada_de"]), {})
        url = longo.get("youtube", "")
        if url.startswith("http"):
            desc = desc.replace("VÍDEO COMPLETO: no canal", f"VÍDEO COMPLETO: {url}")
    return {
        "titulo": (t.get("titulo_youtube") or v["titulo"])[:95],
        "descricao_pronta": desc,
        "legenda_tiktok": t.get("legenda_tiktok") or re.sub(r"#[^\s#]+", "", legenda).strip() or v["titulo"],
        "hashtags_tiktok": hashtags_tt,
        "hashtags": [],
        "tags_youtube": [x.strip() for x in (t.get("tags_youtube") or "").split(",") if x.strip()],
    }


def enviar(v: dict, videos: list[dict], redes: list[str], pasta: Path) -> bool:
    import tiktok_token
    import youtube_token

    if not v.get("mp4"):
        print(f"::error title=Enviar::'{v['titulo']}' não tem MP4 para download (vídeo antigo).")
        return False
    formato = v.get("formato", "curto")
    print(f"⬇️  Baixando {v['titulo']}...")
    arquivo = _baixar(v["mp4"], pasta / Path(v["mp4"]).name)
    capa = _baixar(v["capa"], pasta / Path(v["capa"]).name) if v.get("capa") else None
    r = _roteiro(v, videos)
    ok = True
    for rede in redes:
        if rede == "tiktok" and formato == "longo":
            print("::warning title=TikTok::Vídeo longo horizontal não vai pro TikTok (envie o Short de chamada).")
            continue
        conectado = youtube_token.conectado() if rede == "youtube" else tiktok_token.conectado()
        if not conectado:
            print(f"::error title={rede}::{rede} ainda não está conectado. Use o botão Conectar no painel.")
            ok = False
            continue
        print(f"📤 Enviando para {rede}...")
        try:
            if rede == "youtube":
                import publicar_youtube
                v[rede] = publicar_youtube.publicar(arquivo, r, formato, None, capa)
            else:
                import publicar_tiktok
                v[rede] = publicar_tiktok.publicar(arquivo, r)
            print(f"   {rede}: {v[rede]}")
        except Exception:
            traceback.print_exc()
            v[rede] = "ERRO"
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--redes", default="youtube")
    a = ap.parse_args()
    redes = [x.strip() for x in a.redes.replace("ambos", "youtube,tiktok").split(",") if x.strip()]

    videos = json.loads(PAINEL.read_text(encoding="utf-8"))
    v = next((x for x in videos if _id_de(x) == a.id), None)
    if not v:
        raise SystemExit(f"::error title=Enviar::Vídeo {a.id} não encontrado no painel.")

    pasta = Path(tempfile.mkdtemp())
    ok = enviar(v, videos, redes, pasta)

    # Vídeo longo foi pro YouTube → manda junto o Short de chamada com o link
    if v.get("formato") == "longo" and str(v.get("youtube", "")).startswith("http"):
        for s in videos:
            if s.get("chamada_de") == _id_de(v) and not str(s.get("youtube", "")).startswith("http"):
                ok = enviar(s, videos, ["youtube"], pasta) and ok

    PAINEL.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
