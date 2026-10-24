"""Narração grátis com as vozes neurais da Microsoft (Edge-TTS).
Também devolve o tempo de cada palavra, usado nas legendas."""
import asyncio
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
