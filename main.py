"""
AutoVídeo: tema → roteiro (IA) → narração → vídeo vertical com legendas → YouTube + TikTok.

Uso:
    python main.py                      # gera e publica
    python main.py --sem-publicar       # só gera o vídeo (bom para testar)
    python main.py --tema "buracos negros"
"""
import argparse
import json
import os
import re
import shutil
import traceback
import unicodedata
from datetime import datetime

import config
import roteiro as gerador_roteiro
import video
import voz


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower())[:40].strip("-") or "video"


def _historico() -> list[str]:
    if config.ARQUIVO_HISTORICO.exists():
        return json.loads(config.ARQUIVO_HISTORICO.read_text(encoding="utf-8"))
    return []


def _salvar_historico(lista: list[str]):
    config.ARQUIVO_HISTORICO.write_text(json.dumps(lista[-300:], ensure_ascii=False, indent=1), encoding="utf-8")


def _proximo_tema_da_lista() -> str | None:
    """Pega (e remove) o primeiro tema de temas.txt, se o arquivo existir."""
    if not config.ARQUIVO_TEMAS.exists():
        return None
    linhas = [l for l in config.ARQUIVO_TEMAS.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not linhas:
        return None
    config.ARQUIVO_TEMAS.write_text("\n".join(linhas[1:]) + ("\n" if linhas[1:] else ""), encoding="utf-8")
    return linhas[0].strip()


def _registrar_no_painel(r: dict, resultados: dict):
    """Adiciona o vídeo em docs/videos.json, que o painel (GitHub Pages) mostra."""
    arquivo = config.PASTA / "docs" / "videos.json"
    if not arquivo.parent.exists():
        return
    try:
        lista = json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        lista = []
    item = {"data": datetime.now().astimezone().isoformat(timespec="seconds"),
            "titulo": r["titulo"], "assunto": r.get("assunto", ""), **resultados}
    if os.getenv("GITHUB_RUN_ID"):
        item["download"] = (f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}"
                            f"/actions/runs/{os.getenv('GITHUB_RUN_ID')}")
    lista.append(item)
    arquivo.write_text(json.dumps(lista[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tema", help="assunto específico para este vídeo")
    ap.add_argument("--sem-publicar", action="store_true", help="só gera o vídeo")
    ap.add_argument("--manter-arquivos", action="store_true", help="não apaga clipes e cenas intermediárias")
    args = ap.parse_args()

    historico = _historico()
    tema = args.tema or _proximo_tema_da_lista()

    print("🧠 Escrevendo o roteiro...")
    r = gerador_roteiro.gerar(tema, historico)
    print(f"   → {r['titulo']}")

    pasta = config.PASTA_SAIDA / f"{datetime.now():%Y-%m-%d_%H%M}_{_slug(r['assunto'])}"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "roteiro.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    print("🎙️  Gravando a narração...")
    audio = pasta / "narracao.mp3"
    palavras = voz.gerar(r["roteiro"], audio)

    final = video.montar(r, audio, palavras, pasta)
    destino = pasta / f"{_slug(r['titulo'])}.mp4"
    final.rename(destino)
    print(f"✅ Vídeo pronto: {destino} ({video.duracao(destino):.0f}s)")

    if not args.manter_arquivos:
        for lixo in list(pasta.glob("clipe_*.mp4")) + list(pasta.glob("cena_*.mp4")) + [pasta / "cenas.txt"]:
            lixo.unlink(missing_ok=True)

    historico.append(r["assunto"])
    _salvar_historico(historico)

    if args.sem_publicar:
        _registrar_no_painel(r, {})
        return

    resultados, falhou = {}, False
    if config.PUBLICAR_YOUTUBE:
        print("📤 Publicando no YouTube...")
        try:
            import publicar_youtube
            resultados["youtube"] = publicar_youtube.publicar(destino, r)
        except Exception:
            falhou = True
            resultados["youtube"] = "ERRO"
            traceback.print_exc()
    if config.PUBLICAR_TIKTOK:
        print("📤 Publicando no TikTok...")
        try:
            import publicar_tiktok
            resultados["tiktok"] = publicar_tiktok.publicar(destino, r)
        except Exception:
            falhou = True
            resultados["tiktok"] = "ERRO"
            traceback.print_exc()

    (pasta / "publicacao.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    for rede, res in resultados.items():
        print(f"   {rede}: {res}")
    _registrar_no_painel(r, resultados)
    if falhou:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
