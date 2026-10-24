"""Narração grátis com as vozes neurais da Microsoft (Edge-TTS).
Também devolve o tempo de cada palavra, usado nas legendas."""
import asyncio
import subprocess
from pathlib import Path

import edge_tts

import config


async def _sintetizar(texto: str, destino: Path) -> list[dict]:
    comunicador = edge_tts.Communicate(
        texto,
        config.VOZ,
        rate=config.VELOCIDADE_VOZ,
        boundary="WordBoundary",
    )
    palavras = []
    with open(destino, "wb") as f:
        async for pedaco in comunicador.stream():
            if pedaco["type"] == "audio":
                f.write(pedaco["data"])
            elif pedaco["type"] == "WordBoundary":
                inicio = pedaco["offset"] / 10_000_000  # unidades de 100ns → segundos
                duracao = pedaco["duration"] / 10_000_000
                palavras.append({"inicio": inicio, "fim": inicio + duracao, "texto": pedaco["text"]})
    return palavras


def gerar(texto: str, destino: Path) -> list[dict]:
    """Salva a narração em `destino` (mp3) e retorna a lista de palavras com tempos."""
    for tentativa in range(3):
        try:
            palavras = asyncio.run(_sintetizar(texto, destino))
            if palavras:
                return palavras
        except Exception as erro:  # rede instável, serviço ocupado
            print(f"   voz falhou ({erro}), tentando de novo...")
    raise RuntimeError("Não consegui gerar a narração com o Edge-TTS.")


def _duracao(arquivo: Path) -> float:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(saida.strip())


def gerar_partes(textos: list[str], destino: Path, pausa: float = 0.6) -> tuple[list[dict], list[float]]:
    """Vídeo longo: narra cada parte separada (mais estável que um texto gigante),
    junta tudo com uma pausa entre as partes e devolve (palavras, início de cada parte)."""
    pasta = destino.parent
    lista = pasta / "partes_audio.txt"
    silencio = pasta / "pausa.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", str(pausa), "-q:a", "9", str(silencio)], check=True)

    palavras, inicios, deslocamento = [], [], 0.0
    with open(lista, "w") as f:
        for i, texto in enumerate(textos):
            parte = pasta / f"voz_parte_{i}.mp3"
            ps = gerar(texto, parte)
            inicios.append(deslocamento)
            palavras += [{**p, "inicio": p["inicio"] + deslocamento, "fim": p["fim"] + deslocamento} for p in ps]
            deslocamento += _duracao(parte) + pausa
            f.write(f"file '{parte.name}'\nfile '{silencio.name}'\n")
            print(f"   🎙️  parte {i + 1}/{len(textos)} gravada")

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                    "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "24000", str(destino)], check=True)
    for arquivo in list(pasta.glob("voz_parte_*.mp3")) + [silencio, lista]:
        arquivo.unlink(missing_ok=True)
    return palavras, inicios
