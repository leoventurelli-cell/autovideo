"""Monta o vídeo vertical: clipes do Pexels + narração + legendas animadas."""
import json
import random
import subprocess
from pathlib import Path

import requests

import config

W, H, FPS = config.LARGURA, config.ALTURA, config.FPS
CAUDA = 0.6  # segundos de respiro depois da última palavra


# ───────────────────────── utilidades ─────────────────────────
def _ffmpeg(*args):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{resultado.stderr[-1500:]}")


def duracao(arquivo: Path) -> float:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(arquivo)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(saida)["format"]["duration"])


# ───────────────────────── clipes do Pexels ─────────────────────────
def _buscar_pexels(termo: str, ja_usados: set) -> str | None:
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": termo, "orientation": "portrait", "per_page": 15, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    videos = [v for v in r.json().get("videos", []) if v["id"] not in ja_usados and v["duration"] >= 3]
    if not videos:
        return None
    escolhido = random.choice(videos[:8])
    ja_usados.add(escolhido["id"])
    # arquivo em pé com altura mais próxima de 1920 (sem baixar 4K à toa)
    arquivos = [f for f in escolhido["video_files"] if f.get("height") and f["height"] >= f.get("width", 0)]
    arquivos = arquivos or escolhido["video_files"]
    melhor = min(arquivos, key=lambda f: abs((f.get("height") or 0) - H))
    return melhor["link"]


def baixar_clipes(cenas: list[str], pasta: Path) -> list[Path | None]:
    """Baixa um clipe por cena. Cena sem clipe vira None (usa fundo animado)."""
    if not config.PEXELS_API_KEY:
        print("⚠️  Sem PEXELS_API_KEY: usando fundos animados no lugar dos clipes.")
        return [None] * len(cenas)

    usados, clipes = set(), []
    for i, termo in enumerate(cenas):
        caminho = pasta / f"clipe_{i}.mp4"
        try:
            link = _buscar_pexels(termo, usados) or _buscar_pexels(termo.split()[-1], usados)
            if not link:
                raise ValueError("nenhum resultado")
            with requests.get(link, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(caminho, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            clipes.append(caminho)
            print(f"   🎞️  cena {i + 1}: '{termo}'")
        except Exception as erro:
            print(f"   ⚠️  cena {i + 1} ('{termo}') sem clipe: {erro}")
            clipes.append(None)
    return clipes


# ───────────────────────── legendas ─────────────────────────
def _grupos_de_palavras(palavras: list[dict], maximo=3, pausa=0.35):
    grupos, atual = [], []
    for i, p in enumerate(palavras):
        atual.append(p)
        proxima = palavras[i + 1] if i + 1 < len(palavras) else None
        fim_de_frase = proxima is None or proxima["inicio"] - p["fim"] > pausa
        if len(atual) >= maximo or fim_de_frase:
            grupos.append(atual)
            atual = []
    return grupos


def _tempo_ass(s: float) -> str:
    h, resto = divmod(max(s, 0), 3600)
    m, s = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def criar_legendas(palavras: list[dict], destino: Path):
    """Legenda estilo TikTok: 3 palavras por vez, a palavra falada em destaque."""
    cabecalho = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Padrao,{config.FONTE_LEGENDA},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,80,80,620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    for grupo in _grupos_de_palavras(palavras):
        textos = [p["texto"].replace("{", "").replace("}", "").upper() for p in grupo]
        for i, p in enumerate(grupo):
            inicio = p["inicio"]
            fim = grupo[i + 1]["inicio"] if i + 1 < len(grupo) else p["fim"] + 0.12
            partes = [
                f"{{\\c{config.COR_DESTAQUE}\\fscx112\\fscy112}}{t}{{\\r}}" if j == i else t
                for j, t in enumerate(textos)
            ]
            # pequeno "pop" na entrada do grupo
            efeito = "{\\fad(60,0)}" if i == 0 else ""
            linhas.append(
                f"Dialogue: 0,{_tempo_ass(inicio)},{_tempo_ass(fim)},Padrao,,0,0,0,,{efeito}{' '.join(partes)}"
            )
    destino.write_text(cabecalho + "\n".join(linhas) + "\n", encoding="utf-8")


# ───────────────────────── montagem ─────────────────────────
CORES_FUNDO = [
    ("0x0f2027", "0x2c5364"), ("0x41295a", "0x2f0743"), ("0x16222a", "0x3a6073"),
    ("0x1f1c2c", "0x928dab"), ("0x0b486b", "0xf56217"), ("0x232526", "0x414345"),
]


def _preparar_cena(clipe: Path | None, segundos: float, destino: Path):
    if clipe is None:
        c0, c1 = random.choice(CORES_FUNDO)
        _ffmpeg(
            "-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:speed=0.02:r={FPS}",
            "-t", f"{segundos:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", destino,
        )
        return
    # zoom lento (efeito "Ken Burns") para não ficar parado
    filtro = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"scale={int(W * 1.08)}:-2,crop={W}:{H}:"
        f"(in_w-{W})/2*(1-t/{segundos:.3f}):(in_h-{H})/2,"
        f"setsar=1,fps={FPS},format=yuv420p"
    )
    _ffmpeg(
        "-stream_loop", "-1", "-i", clipe, "-t", f"{segundos:.3f}", "-vf", filtro,
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", destino,
    )


def _tempos_das_cenas(palavras: list[dict], qtd: int, total: float) -> list[float]:
    """Corta as cenas em pontos onde começa uma palavra, para a troca acompanhar a fala."""
    cortes = [0.0]
    for i in range(1, qtd):
        indice = round(i * len(palavras) / qtd)
        cortes.append(palavras[min(indice, len(palavras) - 1)]["inicio"])
    cortes.append(total)
    return [max(fim - ini, 0.5) for ini, fim in zip(cortes, cortes[1:])]


def montar(roteiro: dict, audio: Path, palavras: list[dict], pasta: Path) -> Path:
    total = duracao(audio) + CAUDA
    cenas = roteiro["cenas"][:8] or ["nature"]

    print("🎬 Baixando clipes...")
    clipes = baixar_clipes(cenas, pasta)

    print("✂️  Preparando cenas...")
    lista = pasta / "cenas.txt"
    with open(lista, "w") as f:
        for i, (clipe, seg) in enumerate(zip(clipes, _tempos_das_cenas(palavras, len(cenas), total))):
            cena = pasta / f"cena_{i}.mp4"
            _preparar_cena(clipe, seg, cena)
            f.write(f"file '{cena.name}'\n")

    print("📝 Criando legendas...")
    legendas = pasta / "legendas.ass"
    criar_legendas(palavras, legendas)

    print("🎧 Juntando tudo...")
    final = pasta / "video_final.mp4"
    musicas = sorted(config.PASTA_MUSICA.glob("*.mp3"))
    entradas = ["-f", "concat", "-safe", "0", "-i", lista, "-i", audio]
    if musicas:
        entradas += ["-stream_loop", "-1", "-i", random.choice(musicas)]
        audio_filtro = (
            f"[1:a]apad=pad_dur={CAUDA}[voz];"
            f"[2:a]volume={config.VOLUME_MUSICA},afade=t=out:st={total - 1.5:.2f}:d=1.5[mus];"
            "[voz][mus]amix=inputs=2:duration=first:normalize=0[a]"
        )
    else:
        audio_filtro = f"[1:a]apad=pad_dur={CAUDA}[a]"

    legendas_esc = str(legendas).replace("\\", "/").replace(":", "\\:")
    fontes_esc = str(config.PASTA_FONTES).replace("\\", "/").replace(":", "\\:")
    _ffmpeg(
        *entradas,
        "-filter_complex",
        f"[0:v]ass='{legendas_esc}':fontsdir='{fontes_esc}'[v];{audio_filtro}",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        final,
    )
    return final
