"""Cria (de novo) a thumbnail com IA de um vídeo do painel e coloca no YouTube.

Uso:  python capa.py --id video-20261025-1031-14
"""
import argparse
import json
import re
import tempfile
from pathlib import Path

import config
import roteiro
import video
from enviar import PAINEL, _baixar, _id_de

PROMPT = """Crie a thumbnail de um vídeo do YouTube em {idioma}.
Título: {titulo}
Assunto: {assunto}
Responda SOMENTE com um JSON:
{{"texto_capa": "2 a 4 palavras de impacto que despertem curiosidade (ex: 'NINGUÉM EXPLICA ISSO')",
  "prompt_capa": "descrição EM INGLÊS de UMA cena cinematográfica e chamativa do tema (objeto/lugar principal em close, iluminação dramática), sem texto"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    a = ap.parse_args()
    videos = json.loads(PAINEL.read_text(encoding="utf-8"))
    v = next((x for x in videos if _id_de(x) == a.id), None)
    if not v:
        raise SystemExit(f"::error title=Capa::Vídeo {a.id} não encontrado no painel.")
    m = re.search(r"(?:youtu\.be/|shorts/)([\w-]{6,})", str(v.get("youtube", "")))
    if not m:
        raise SystemExit("::error title=Capa::Esse vídeo ainda não está no YouTube.")
    video_id = m.group(1)

    pasta = Path(tempfile.mkdtemp())
    arquivo = _baixar(v["mp4"], pasta / Path(v["mp4"]).name)
    textos = roteiro._pedir_ao_groq(PROMPT.format(idioma=config.IDIOMA, titulo=v["titulo"], assunto=v.get("assunto", "")))
    capa = video.criar_capa(arquivo, textos.get("texto_capa") or v["titulo"], pasta / f"{a.id}-capa.jpg",
                            prompt_ia=textos.get("prompt_capa") or v.get("assunto"))

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import publicar_youtube
    yt = build("youtube", "v3", credentials=publicar_youtube._credenciais(), cache_discovery=False)
    yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(capa), mimetype="image/jpeg")).execute()
    print(f"::notice title=Capa enviada::https://youtu.be/{video_id} → '{textos.get('texto_capa')}'")
    (config.PASTA_SAIDA / "capa.txt").parent.mkdir(parents=True, exist_ok=True)
    (config.PASTA_SAIDA / "capa.txt").write_text(f"{a.id}\n{capa}", encoding="utf-8")


if __name__ == "__main__":
    main()
