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
    try:
        resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg travou (mais de 15 min)")
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{resultado.stderr[-1500:]}")


def _ganho_para(audio: Path, alvo: float = -14.0) -> float:
    """Mede o volume da narração (LUFS) e devolve quantos dB somar para chegar no alvo."""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), "-af",
                            "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
        medido = float(json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])["input_i"])
        return max(-10.0, min(20.0, alvo - medido))
    except Exception as erro:
        print(f"   (não consegui medir o volume: {erro}; usando +6 dB)")
        return 6.0


def duracao(arquivo: Path) -> float:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(arquivo)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(saida)["format"]["duration"])


# ───────────────────────── clipes do Pexels ─────────────────────────
def _buscar_pexels(termo: str, ja_usados: set, exigir_relevancia: bool = False) -> str | None:
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
    # escolhe pelo que o vídeo REALMENTE mostra (a descrição vem no endereço do Pexels),
    # e evita cenas genéricas de escritório/negócios que não combinam com o assunto
    vazias = {"photo", "video", "image", "footage", "view", "scene", "shot", "close", "the", "and", "with",
              "blurred", "dark", "bright", "old", "night", "cinematic", "people", "man", "woman"}
    palavras_termo = {w for w in termo.lower().replace("-", " ").split() if len(w) > 2} - vazias
    genericas = {"office", "business", "meeting", "handshake", "laptop", "stock", "trading", "kitchen",
                 "corporate", "businessman", "businesswoman", "coworkers", "presentation", "typing"}

    def nota(v):
        slug = set(v.get("url", "").lower().rstrip("/").split("/")[-1].replace("-", " ").split())
        pontos = 3 * len(palavras_termo & slug)
        if (slug & genericas) and not (palavras_termo & genericas):
            pontos -= 5
        return pontos

    ordenados = sorted(enumerate(videos), key=lambda iv: (-nota(iv[1]), iv[0]))
    melhores = [v for _, v in ordenados[:2]]
    # o vídeo precisa mostrar pelo menos metade das palavras importantes da cena (ex.: 'military truck'
    # precisa de 'military' E 'truck'; 'radio telescope' precisa de 'telescope' e 'radio')
    minimo = 3 * max(1, -(-len(palavras_termo) // 2))
    if exigir_relevancia and palavras_termo and nota(melhores[0]) < minimo:
        return None  # nenhum vídeo mostra de fato o que a cena pede
    escolhido = random.choice(melhores) if nota(melhores[0]) == nota(melhores[-1]) else melhores[0]
    ja_usados.add(escolhido["id"])
    deitado = P["orientacao"] == "landscape"
    arquivos = [f for f in escolhido["video_files"] if f.get("height") and f.get("width")
                and ((f["width"] >= f["height"]) == deitado)]
    arquivos = arquivos or escolhido["video_files"]
    # o mais próximo da resolução final (sem baixar 4K à toa)
    melhor = min(arquivos, key=lambda f: abs((f.get("height") or 0) - H))
    return melhor["link"]


IMAGINARIOS = (" alien", "ufo", "spaceship", "space ship", "spacecraft", "flying saucer", "extraterrestrial",
               "creature", "monster", "ghost", "humanoid", " et ", "mothership", "abduction", "cryptid",
               "haunted", "apparition", "spirit ", "shadow figure", "poltergeist", "demon", "possessed", "phantom")
CREDITOS: list[str] = []  # créditos das fotos da Wikimedia usadas no vídeo (vão para a descrição)
UA = {"User-Agent": "AutoVideoBot/1.0 (https://github.com/leoventurelli-cell/autovideo)"}


def _normalizar_foto(arquivo: Path):
    """Regrava qualquer imagem (PNG, GIF, TIFF, WebP...) como JPEG RGB de tamanho razoável,
    para o FFmpeg abrir sem surpresa."""
    from PIL import Image
    with Image.open(arquivo) as im:
        im.seek(0)
        im = im.convert("RGB")
        im.thumbnail((2400, 2400))
        im.save(arquivo, "JPEG", quality=92)


# apelidos que na Wikipédia são outra coisa (ex.: "Lula" em português é o molusco)
APELIDOS = {"lula": "Luiz Inácio Lula da Silva", "bolsonaro": "Jair Bolsonaro", "jair bolsonaro": "Jair Bolsonaro",
            "moraes": "Alexandre de Moraes", "xandão": "Alexandre de Moraes", "dilma": "Dilma Rousseff",
            "fhc": "Fernando Henrique Cardoso", "temer": "Michel Temer", "alckmin": "Geraldo Alckmin",
            "flávio": "Flávio Bolsonaro", "eduardo bolsonaro": "Eduardo Bolsonaro", "tarcísio": "Tarcísio de Freitas",
            "trump": "Donald Trump", "milei": "Javier Milei", "pelé": "Pelé", "neymar": "Neymar", "stf": "Supremo Tribunal Federal",
            "pf": "Polícia Federal (Brasil)", "tse": "Tribunal Superior Eleitoral"}
# descrição de página que indica que a Wikipédia achou um bicho/planta ou uma página de desambiguação
NAO_E_ISSO = ("espécie", "género", "gênero", "ordem de", "molusco", "cefalópode", "família de", "species", "genus",
              "order of", "desambigua", "disambiguation", "página de")


def _foto_wikimedia(nome: str, destino: Path) -> bool:
    """Foto real (pessoa, lugar, objeto) da Wikipédia, só se o arquivo estiver no Wikimedia Commons
    (licença livre). Guarda autor e licença em CREDITOS."""
    import html
    import re as _re
    nome = APELIDOS.get(nome.strip().lower(), nome.strip())
    for lingua in ("pt", "en"):
        try:
            r = requests.get(f"https://{lingua}.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
                "action": "query", "titles": nome, "prop": "pageimages|pageprops|description",
                "piprop": "original|name", "redirects": 1, "format": "json"}).json()
            pagina = next(iter(r.get("query", {}).get("pages", {}).values()), {})
            arquivo = pagina.get("pageimage")
            descricao = str(pagina.get("description", "")).lower()
            if "disambiguation" in pagina.get("pageprops", {}) or any(p in descricao for p in NAO_E_ISSO):
                print(f"   '{nome}' na Wikipédia ({lingua}) é outra coisa: {descricao or 'desambiguação'}")
                continue
            if not arquivo:
                continue
            info = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
                "action": "query", "titles": f"File:{arquivo}", "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": 1920, "format": "json"}).json()
            pag = next(iter(info.get("query", {}).get("pages", {}).values()), {})
            ii = (pag.get("imageinfo") or [None])[0]
            if not ii or "/wikipedia/commons/" not in ii.get("url", ""):
                continue  # imagem só da Wikipédia (uso restrito): não usa
            meta = ii.get("extmetadata", {})
            autor = _re.sub("<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", ""))).strip()
            licenca = meta.get("LicenseShortName", {}).get("value", "")
            url = ii.get("thumburl") or ii["url"]
            img = requests.get(url, headers=UA, timeout=60)
            img.raise_for_status()
            destino.write_bytes(img.content)
            _normalizar_foto(destino)
            CREDITOS.append(f"{nome}: {autor or 'Wikimedia Commons'} ({licenca}, Wikimedia Commons)")
            return True
        except Exception as erro:
            print(f"   foto de '{nome}' indisponível ({erro})")
    return False


def baixar_clipes(cenas: list[str], pasta: Path) -> dict[str, Path | None]:
    """Uma mídia por termo (sem repetir termos):
       'wiki:Nome'  → foto real da Wikimedia (pessoas, lugares, objetos famosos)
       'ia:cena'    → imagem gerada por IA (ET, nave, criaturas, cenas imaginadas)
       outro termo  → vídeo do Pexels; se nada combinar, imagem de IA da mesma cena.
    Termo sem nada vira None (fundo animado)."""
    unicos = list(dict.fromkeys(cenas))
    usados, clipes = set(), {}
    for i, termo in enumerate(unicos):
        tipo, _, valor = termo.partition(":") if termo.split(":", 1)[0] in ("wiki", "ia") else ("", "", termo)
        valor = valor.strip()
        if not tipo and any(p in f" {termo.lower()} " for p in IMAGINARIOS):
            tipo = "ia"  # banco de vídeo não tem ET/nave de verdade: desenha a cena
        if tipo == "wiki":
            foto = pasta / f"clipe_{i}.jpg"
            if _foto_wikimedia(valor, foto):
                clipes[termo] = foto
                print(f"   🖼️  foto real {i + 1}/{len(unicos)}: '{valor}'")
                continue
            tipo = "ia"  # sem foto livre: desenha a cena
        if tipo == "ia" or not config.PEXELS_API_KEY:
            img = pasta / f"clipe_{i}.jpg"
            if _imagem_ia(f"{valor}, realistic cinematic photo, vertical composition" if P["orientacao"] == "portrait"
                          else f"{valor}, realistic cinematic photo", img, rapido=True):
                clipes[termo] = img
                print(f"   🎨 imagem IA {i + 1}/{len(unicos)}: '{valor}'")
            else:
                clipes[termo] = None
            continue
        caminho = pasta / f"clipe_{i}.mp4"
        try:
            link = _buscar_pexels(termo, usados, exigir_relevancia=True)
            if not link:
                img = pasta / f"clipe_{i}.jpg"
                if _imagem_ia(f"{termo}, realistic cinematic photo", img, rapido=True):
                    clipes[termo] = img
                    print(f"   🎨 imagem IA {i + 1}/{len(unicos)}: '{termo}' (sem vídeo que combine)")
                    continue
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
    # cena de IA que falhou: repete uma imagem de IA que deu certo (ET/nave) em vez de fundo vazio
    feitas = [c for c in clipes.values() if c and c.suffix == ".jpg" and c.name.startswith("clipe_")]
    for termo in unicos:
        if clipes.get(termo) is None and feitas:
            clipes[termo] = random.choice(feitas)
            print(f"   ↺ '{termo}' reaproveita {clipes[termo].name}")
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
        margem = 330 if H > W else 0  # no Short, abaixo da barra do topo do TikTok/YouTube
        linhas.append(f"Dialogue: 1,{_tempo_ass(inicio)},{_tempo_ass(inicio + 3.5)},Titulo,,0,0,{margem},,"
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
    if clipe.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            _normalizar_foto(clipe)  # imagem quebrada falha aqui, antes do FFmpeg
            return _cena_de_foto(clipe, segundos, destino)
        except Exception as erro:
            print(f"   ⚠️  foto {clipe.name} não abriu ({str(erro)[-120:]}); usando fundo animado")
            return _preparar_cena(None, segundos, destino)
    _cena_de_video(clipe, segundos, destino, inicio_clipe)


def _cena_de_foto(clipe: Path, segundos: float, destino: Path):
    if True:
        # foto: fundo desfocado preenchendo a tela + a foto inteira por cima, com zoom lento
        quadros = max(1, int(segundos * FPS))
        zoom = "1+0.10*on/" + str(quadros) if random.random() < 0.5 else "1.10-0.10*on/" + str(quadros)
        _ffmpeg(
            "-loop", "1", "-i", clipe, "-filter_complex",
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.15[f];"
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[a];"
            f"[f][a]overlay=(W-w)/2:(H-h)/2,scale={W * 2}:{H * 2},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={quadros}:s={W}x{H}:fps={FPS},"
            "setsar=1,format=yuv420p",
            "-t", f"{segundos:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", destino,
        )


def _cena_de_video(clipe: Path, segundos: float, destino: Path, inicio_clipe: float = 0.0):
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
        # gancho escrito na tela nos primeiros segundos: quem passa o dedo lê antes mesmo de ouvir
        gancho = str(roteiro.get("texto_capa") or "").strip()
        titulos = [(0.05, gancho)] if gancho else None

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
    # volume no padrão das redes (~-14 LUFS) com ganho FIXO (medido antes) + limitador suave:
    # o loudnorm dinâmico ficava subindo/abaixando o som e "cortava" o começo das frases.
    ganho = _ganho_para(audio, alvo=-14.0)
    audio_filtro += (f";[a0]volume={ganho:.1f}dB,alimiter=limit=0.89:attack=5:release=80:level=false,"
                     "aformat=sample_rates=48000:channel_layouts=stereo[a]")

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
# o serviço grátis de imagens às vezes fica lotado: para não atrasar o horário do vídeo,
# depois de 2 falhas seguidas (ou 8 minutos gastos) as cenas usam fotos reais / banco de vídeo
_IA = {"inicio": None, "falhas_seguidas": 0}
LIMITE_IA_SEGUNDOS = 8 * 60


def _imagem_ia(prompt: str, destino: Path, rapido: bool = False) -> bool:
    """Gera uma imagem do tema com IA grátis (Pollinations, sem chave). False se falhar."""
    from urllib.parse import quote
    if rapido:
        _IA["inicio"] = _IA["inicio"] or time.time()
        if _IA["falhas_seguidas"] >= 2 or time.time() - _IA["inicio"] > LIMITE_IA_SEGUNDOS:
            return False  # serviço lotado hoje: não espera mais
    estilo = ("cinematic YouTube thumbnail background, dramatic lighting, high contrast, vivid colors, "
              "sharp focus, mysterious atmosphere, no text, no letters, no watermark")
    if rapido:  # imagem de cena do vídeo (não é capa)
        estilo = "photorealistic, cinematic lighting, high detail, no text, no letters, no watermark"
    larg, alt = (1080, 1920) if (rapido and P["orientacao"] == "portrait") else (1280, 720)
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt + ', ' + estilo)}"
           f"?width={larg}&height={alt}&nologo=true&enhance=true&seed={random.randint(1, 99999)}")
    cab = {"User-Agent": "Mozilla/5.0 (AutoVideo; +https://github.com)", "Accept": "image/*"}
    for tentativa in range(2 if rapido else 4):
        try:
            r = requests.get(url + ("&referrer=autovideo" if tentativa % 2 else ""), headers=cab,
                             timeout=60 if rapido else 150)
            tipo = r.headers.get("content-type", "")
            if r.ok and tipo.startswith("image"):
                destino.write_bytes(r.content)
                _normalizar_foto(destino)
                _IA["falhas_seguidas"] = 0
                return True
            print(f"   imagem IA: tentativa {tentativa + 1} → {r.status_code} (servidor ocupado)")
            if r.status_code in (402, 429):
                time.sleep(10 if rapido else 25)  # limite de pedidos do serviço grátis: espera a fila andar
        except Exception as erro:
            print(f"   imagem IA: tentativa {tentativa + 1} falhou ({erro})")
        time.sleep(4 if rapido else 8)
    if rapido:
        _IA["falhas_seguidas"] += 1
        if _IA["falhas_seguidas"] == 2:
            print("::warning title=Imagens de IA::serviço de imagens lotado; as próximas cenas usam fotos reais e banco de vídeo.")
    if not rapido:
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
