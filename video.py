"""Monta o vídeo: clipes do Pexels + narração + legendas animadas.

Dois formatos:
  curto → vertical 1080x1920 (TikTok / Shorts), legenda grande no meio
  longo → horizontal 1920x1080 (YouTube), legenda embaixo e título de cada parte
"""
import json
import random
import subprocess
import time
from pathlib import Path

import requests

import config

FPS = config.FPS
CAUDA = 0.6  # segundos de respiro depois da última palavra

PERFIS = {
    "curto": dict(w=1080, h=1920, orientacao="portrait", fonte=96, contorno=7, margem=620,
                  palavras_por_vez=3, seg_cena=None),
    "longo": dict(w=1920, h=1080, orientacao="landscape", fonte=64, contorno=5, margem=70,
                  palavras_por_vez=5, seg_cena=7.0),
}
P = PERFIS["curto"]
W, H = P["w"], P["h"]


def usar_formato(formato: str):
    global P, W, H
    P = PERFIS[formato]
    W, H = P["w"], P["h"]


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
        params={"query": termo, "orientation": P["orientacao"], "per_page": 15, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    videos = [v for v in r.json().get("videos", []) if v["id"] not in ja_usados and v["duration"] >= 4]
    if not videos:
        return None
    escolhido = random.choice(videos[:8])
    ja_usados.add(escolhido["id"])
    deitado = P["orientacao"] == "landscape"
    arquivos = [f for f in escolhido["video_files"] if f.get("height") and f.get("width")
                and ((f["width"] >= f["height"]) == deitado)]
    arquivos = arquivos or escolhido["video_files"]
    # o mais próximo da resolução final (sem baixar 4K à toa)
    melhor = min(arquivos, key=lambda f: abs((f.get("height") or 0) - H))
    return melhor["link"]


def baixar_clipes(cenas: list[str], pasta: Path) -> dict[str, Path | None]:
    """Baixa um clipe por termo (sem repetir termos). Termo sem clipe vira None (fundo animado)."""
    unicos = list(dict.fromkeys(cenas))
    if not config.PEXELS_API_KEY:
        print("⚠️  Sem PEXELS_API_KEY: usando fundos animados no lugar dos clipes.")
        return {t: None for t in unicos}

    usados, clipes = set(), {}
    for i, termo in enumerate(unicos):
        caminho = pasta / f"clipe_{i}.mp4"
        try:
            link = _buscar_pexels(termo, usados) or _buscar_pexels(termo.split()[-1], usados)
            if not link:
                raise ValueError("nenhum resultado")
            with requests.get(link, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(caminho, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            clipes[termo] = caminho
            print(f"   🎞️  clipe {i + 1}/{len(unicos)}: '{termo}'")
        except Exception as erro:
            print(f"   ⚠️  '{termo}' sem clipe: {erro}")
            clipes[termo] = None
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


def _limpo(t: str) -> str:
    return str(t).replace("{", "").replace("}", "").replace("\n", " ")


def criar_legendas(palavras: list[dict], destino: Path, titulos: list[tuple[float, str]] | None = None):
    """Legenda palavra a palavra com destaque; no longo, também o título de cada parte."""
    cabecalho = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Padrao,{config.FONTE_LEGENDA},{P['fonte']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{P['contorno']},3,2,80,80,{P['margem']},1
Style: Titulo,{config.FONTE_LEGENDA},{int(P['fonte'] * 1.25)},&H0000E5FF,&H0000E5FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    for inicio, titulo in titulos or []:
        linhas.append(f"Dialogue: 1,{_tempo_ass(inicio)},{_tempo_ass(inicio + 3.5)},Titulo,,0,0,0,,"
                      f"{{\\fad(250,300)}}{_limpo(titulo).upper()}")
    for grupo in _grupos_de_palavras(palavras, maximo=P["palavras_por_vez"]):
        textos = [_limpo(p["texto"]).upper() for p in grupo]
        for i, p in enumerate(grupo):
            inicio = p["inicio"]
            fim = grupo[i + 1]["inicio"] if i + 1 < len(grupo) else p["fim"] + 0.12
            partes = [
                f"{{\\c{config.COR_DESTAQUE}\\fscx112\\fscy112}}{t}{{\\r}}" if j == i else t
                for j, t in enumerate(textos)
            ]
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


def _preparar_cena(clipe: Path | None, segundos: float, destino: Path, inicio_clipe: float = 0.0):
    if clipe is None:
        c0, c1 = random.choice(CORES_FUNDO)
        _ffmpeg(
            "-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:speed=0.02:r={FPS}",
            "-t", f"{segundos:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", destino,
        )
        return
    # zoom lento (efeito "Ken Burns"), alternando a direção, para não ficar parado
    ida = random.random() < 0.5
    x = f"(in_w-{W})/2*(1-t/{segundos:.3f})" if ida else f"(in_w-{W})/2*(t/{segundos:.3f})"
    filtro = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"scale={int(W * 1.08)}:-2,crop={W}:{H}:{x}:(in_h-{H})/2,"
        f"setsar=1,fps={FPS},format=yuv420p"
    )
    entrada = ["-stream_loop", "-1"]
    if inicio_clipe > 0:
        inicio_clipe = inicio_clipe % max(duracao(clipe) - 1.0, 1.0)
    if inicio_clipe > 0.1:
        entrada += ["-ss", f"{inicio_clipe:.2f}"]
    _ffmpeg(
        *entrada, "-i", clipe, "-t", f"{segundos:.3f}", "-vf", filtro,
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", destino,
    )


def _plano_curto(roteiro: dict, palavras: list[dict], total: float) -> list[tuple[str, float]]:
    """Curto: uma cena por termo, cortes nos inícios de palavra."""
    cenas = roteiro["cenas"][:12] or ["nature"]
    cortes = [0.0]
    for i in range(1, len(cenas)):
        indice = round(i * len(palavras) / len(cenas))
        cortes.append(palavras[min(indice, len(palavras) - 1)]["inicio"])
    cortes.append(total)
    return [(c, max(fim - ini, 0.5)) for c, ini, fim in zip(cenas, cortes, cortes[1:])]


def _plano_longo(roteiro: dict, inicios: list[float], total: float) -> list[tuple[str, float]]:
    """Longo: cada parte é picada em cenas de ~7s, alternando os termos daquela parte."""
    plano = []
    limites = inicios + [total]
    for parte, ini, fim in zip(roteiro["partes"], limites, limites[1:]):
        termos = parte["cenas"]
        tamanho = fim - ini
        qtd = max(1, round(tamanho / P["seg_cena"]))
        for j in range(qtd):
            plano.append((termos[j % len(termos)], tamanho / qtd))
    return plano


def montar(roteiro: dict, audio: Path, palavras: list[dict], pasta: Path,
           formato: str = "curto", inicios_partes: list[float] | None = None) -> Path:
    usar_formato(formato)
    total = duracao(audio) + CAUDA
    if formato == "longo":
        plano = _plano_longo(roteiro, inicios_partes, total)
        titulos = [(ini + 0.2, p["titulo"]) for p, ini in zip(roteiro["partes"], inicios_partes)][1:]
    else:
        plano = _plano_curto(roteiro, palavras, total)
        titulos = None

    print(f"🎬 Baixando clipes ({len(set(t for t, _ in plano))} temas, {len(plano)} cenas)...")
    clipes = baixar_clipes([t for t, _ in plano], pasta)

    print("✂️  Preparando cenas...")
    lista = pasta / "cenas.txt"
    vezes: dict[str, int] = {}
    with open(lista, "w") as f:
        for i, (termo, seg) in enumerate(plano):
            uso = vezes.get(termo, 0)
            vezes[termo] = uso + 1
            cena = pasta / f"cena_{i}.mp4"
            # quando o mesmo clipe se repete, começa de outro ponto dele
            _preparar_cena(clipes.get(termo), seg, cena, inicio_clipe=uso * 3.0)
            f.write(f"file '{cena.name}'\n")
            if formato == "longo" and (i + 1) % 10 == 0:
                print(f"   {i + 1}/{len(plano)} cenas prontas")

    print("📝 Criando legendas...")
    legendas = pasta / "legendas.ass"
    criar_legendas(palavras, legendas, titulos)

    print("🎧 Juntando tudo...")
    final = pasta / "video_final.mp4"
    musicas = sorted(config.PASTA_MUSICA.glob("*.mp3"))
    entradas = ["-f", "concat", "-safe", "0", "-i", lista, "-i", audio]
    if musicas:
        entradas += ["-stream_loop", "-1", "-i", random.choice(musicas)]
        audio_filtro = (
            f"[1:a]apad=pad_dur={CAUDA}[voz];"
            f"[2:a]volume={config.VOLUME_MUSICA},afade=t=out:st={total - 1.5:.2f}:d=1.5[mus];"
            "[voz][mus]amix=inputs=2:duration=first:normalize=0[a0]"
        )
    else:
        audio_filtro = f"[1:a]apad=pad_dur={CAUDA}[a0]"
    # volume no padrão das redes (-14 LUFS) e em estéreo 48 kHz: áudio mono e baixo
    # às vezes sai mudo/fraco no TikTok
    audio_filtro += ";[a0]loudnorm=I=-14:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[a]"

    legendas_esc = str(legendas).replace("\\", "/").replace(":", "\\:")
    fontes_esc = str(config.PASTA_FONTES).replace("\\", "/").replace(":", "\\:")
    _ffmpeg(
        *entradas,
        "-filter_complex",
        f"[0:v]ass='{legendas_esc}':fontsdir='{fontes_esc}'[v];{audio_filtro}",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21" if formato == "longo" else "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        final,
    )
    return final


# ───────────────────────── thumbnail (capa) ─────────────────────────
def _imagem_ia(prompt: str, destino: Path) -> bool:
    """Gera uma imagem do tema com IA grátis (Pollinations, sem chave). False se falhar."""
    from urllib.parse import quote
    from PIL import Image
    estilo = ("cinematic YouTube thumbnail background, dramatic lighting, high contrast, vivid colors, "
              "sharp focus, mysterious atmosphere, no text, no letters, no watermark")
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt + ', ' + estilo)}"
           f"?width=1280&height=720&nologo=true&enhance=true&seed={random.randint(1, 99999)}")
    cab = {"User-Agent": "Mozilla/5.0 (AutoVideo; +https://github.com)", "Accept": "image/*"}
    for tentativa in range(4):
        try:
            r = requests.get(url + ("&referrer=autovideo" if tentativa % 2 else ""), headers=cab, timeout=150)
            tipo = r.headers.get("content-type", "")
            if r.ok and tipo.startswith("image"):
                destino.write_bytes(r.content)
                Image.open(destino).verify()
                return True
            print(f"   capa IA: tentativa {tentativa + 1} → {r.status_code} {tipo} {r.text[:150]!r}")
        except Exception as erro:
            print(f"   capa IA: tentativa {tentativa + 1} falhou ({erro})")
        time.sleep(8)
    print("::warning title=Capa::A IA de imagem não respondeu; usei uma cena do vídeo.")
    return False


def criar_capa(video_mp4: Path, titulo: str, destino: Path, prompt_ia: str | None = None) -> Path:
    """Capa 1280x720 para o YouTube: imagem do tema feita por IA (ou um quadro do vídeo)
    + frase curta e grande, no estilo das capas que mais recebem cliques."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont

    fundo = destino.with_suffix(".fundo.jpg")
    usou_ia = bool(prompt_ia) and _imagem_ia(prompt_ia, fundo)
    if usou_ia:
        img = Image.open(fundo).convert("RGB")
        w, h = img.size  # amplia ~7% e corta: some a marca d'água do canto
        img = img.resize((int(w * 1.07), int(h * 1.07)), Image.LANCZOS)
        img = img.crop((0, 0, w, h)).resize((1280, 720), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(1.12)
        print("   🖼️  capa criada com imagem de IA")
    else:
        # cena do vídeo sem a faixa de legenda (corta a parte de baixo, onde ela fica)
        _ffmpeg("-ss", f"{duracao(video_mp4) * 0.3:.1f}", "-i", video_mp4, "-frames:v", "1",
                "-vf", "crop=iw:ih*0.74:0:0,scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720", fundo)
        img = Image.open(fundo).convert("RGB")

    # escurece o lado esquerdo (onde vai o texto) com um degradê
    sombra = Image.new("L", (1280, 720))
    ds = ImageDraw.Draw(sombra)
    for x in range(1280):
        ds.line([(x, 0), (x, 720)], fill=int(215 * max(0.0, 1 - x / 900) ** 1.3))
    img = Image.composite(Image.new("RGB", (1280, 720), (0, 0, 0)), img, sombra)
    d = ImageDraw.Draw(img)
    fonte_arq = str(config.PASTA_FONTES / "Poppins-Bold.ttf")

    palavras = titulo.upper().split()
    tamanho = 150
    while True:  # até 3 linhas na metade esquerda
        fonte = ImageFont.truetype(fonte_arq, tamanho)
        linhas, atual = [], ""
        for p in palavras:
            teste = f"{atual} {p}".strip()
            if d.textlength(teste, font=fonte) <= 760:
                atual = teste
            else:
                if atual:
                    linhas.append(atual)
                atual = p
        linhas.append(atual)
        if (len(linhas) <= 3 and max(d.textlength(l, font=fonte) for l in linhas) <= 800) or tamanho <= 64:
            break
        tamanho -= 8

    altura_linha = int(tamanho * 1.08)
    y = (720 - altura_linha * len(linhas)) // 2
    for n, linha in enumerate(linhas):
        cor = "#FFE500" if n == len(linhas) - 1 else "#FFFFFF"  # última linha em amarelo
        d.text((56, y), linha, font=fonte, fill=cor, stroke_width=max(5, tamanho // 12), stroke_fill="#000000")
        y += altura_linha
    # faixa vermelha fina embaixo do texto
    d.rectangle((60, y + 22, 60 + 220, y + 36), fill="#FF1E1E")
    img.save(destino, "JPEG", quality=92)
    fundo.unlink(missing_ok=True)
    return destino


# ───────────────────────── Short de chamada para o vídeo longo ─────────────────────────
def _quebrar(d, texto, fonte, largura_max):
    linhas, atual = [], ""
    for p in texto.split():
        teste = f"{atual} {p}".strip()
        if d.textlength(teste, font=fonte) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def criar_chamada(video_longo: Path, titulo: str, destino: Path, segundos: float = 58.0,
                  inicio: float = 0.0) -> Path:
    """Short vertical (1080x1920) com o começo do vídeo longo + faixas
    "VÍDEO COMPLETO NO CANAL", para levar o público do Shorts até o vídeo longo."""
    from PIL import Image, ImageDraw, ImageFont

    total = duracao(video_longo)
    segundos = max(10.0, min(segundos, total - inicio))
    fonte_arq = str(config.PASTA_FONTES / "Poppins-Bold.ttf")

    # camada transparente com os textos (desenhada no Pillow, não depende do drawtext do FFmpeg)
    cam = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(cam)
    tam = 84
    while True:
        f = ImageFont.truetype(fonte_arq, tam)
        linhas = _quebrar(d, titulo.upper(), f, 980)
        if len(linhas) <= 4 or tam <= 52:
            break
        tam -= 6
    alt = int(tam * 1.15)
    y = 610 - alt * len(linhas)  # o vídeo começa em y=656
    for n, linha in enumerate(linhas):
        largura = d.textlength(linha, font=f)
        d.text(((1080 - largura) / 2, y), linha, font=f, fill="#FFE500" if n == 0 else "#FFFFFF",
               stroke_width=max(4, tam // 12), stroke_fill="#000000")
        y += alt

    # faixa de baixo
    d.rounded_rectangle((90, 1360, 990, 1530), radius=36, fill=(255, 0, 0, 235))
    f2 = ImageFont.truetype(fonte_arq, 54)
    t2 = "ASSISTA O VÍDEO COMPLETO"
    for texto, fonte, yy in ((t2, f2, 1378), ("NO CANAL  •  LINK NA DESCRIÇÃO", ImageFont.truetype(fonte_arq, 40), 1458)):
        largura = d.textlength(texto, font=fonte)
        d.text(((1080 - largura) / 2, yy), texto, font=fonte, fill="#FFFFFF")
    camada = destino.with_suffix(".camada.png")
    cam.save(camada)

    fade = max(0.0, segundos - 1.2)
    _ffmpeg(
        "-ss", f"{inicio:.2f}", "-t", f"{segundos:.2f}", "-i", video_longo, "-i", camada,
        "-filter_complex",
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.18[fundo];"
        "[b]scale=1080:-2[frente];"
        "[fundo][frente]overlay=0:656[base];"
        f"[base][1:v]overlay=0:0,fade=t=out:st={fade:.2f}:d=1.2,format=yuv420p[v];"
        f"[0:a]afade=t=out:st={fade:.2f}:d=1.2[aud]",
        "-map", "[v]", "-map", "[aud]", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", destino,
    )
    camada.unlink(missing_ok=True)
    return destino
