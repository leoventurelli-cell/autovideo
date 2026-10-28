"""Cria a cópia leve de um Short que já está no painel, para o botão "Mandar pro TikTok" do celular.

Uso:  python celular.py --id video-20261028-1141-42
"""
import argparse
import json
import tempfile
from pathlib import Path

from enviar import PAINEL, _baixar, _id_de
from main import copia_para_celular


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    a = ap.parse_args()
    videos = json.loads(PAINEL.read_text(encoding="utf-8"))
    v = next((x for x in videos if _id_de(x) == a.id), None)
    if not v or not v.get("mp4"):
        raise SystemExit(f"::error title=Celular::Vídeo {a.id} não encontrado (ou sem MP4).")
    if v.get("formato") == "longo":
        raise SystemExit("::error title=Celular::Vídeo longo não vai para o TikTok; use o Short de chamada.")
    arquivo = _baixar(v["mp4"], Path(tempfile.mkdtemp()) / Path(v["mp4"]).name)
    v["celular"] = copia_para_celular(arquivo, a.id)
    if not v["celular"]:
        raise SystemExit(1)
    PAINEL.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ pronto para o celular: {v['celular']}")


if __name__ == "__main__":
    main()
