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


def _legenda(r: dict) -> str:
    """Legenda pronta para colar no TikTok (gancho + pergunta + hashtags)."""
    if r.get("legenda_tiktok"):
        return f"{r['legenda_tiktok']}\n\n{' '.join(r.get('hashtags_tiktok', []))}".strip()
    return f"{r['titulo']}\n\n{r.get('descricao', '')}\n\n{' '.join(r.get('hashtags', []))}".strip()


def _url_release(tag: str, arquivo) -> str | None:
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        return None
    return f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/releases/download/{tag}/{arquivo.name}"


def _preparar_download(r: dict, destino, capa=None, extras=()) -> tuple[str | None, str | None]:
    """No GitHub, o MP4 (e a capa) viram um 'Release' público com link direto de download.
    Aqui só anotamos os nomes; o envio dos arquivos é feito pelo workflow."""
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        return None, None
    tag = f"video-{datetime.now():%Y%m%d-%H%M}-{os.getenv('GITHUB_RUN_NUMBER', '0')}"
    arquivos = [str(destino)] + ([str(capa)] if capa else []) + [str(e) for e in extras]
    r["_tag"] = tag
    (config.PASTA_SAIDA / "release.json").write_text(json.dumps({
        "tag": tag, "arquivos": arquivos, "titulo": r["titulo"][:120], "legenda": _legenda(r),
    }, ensure_ascii=False), encoding="utf-8")
    base = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/releases/download/{tag}"
    return f"{base}/{destino.name}", (f"{base}/{capa.name}" if capa else None)


def _textos_para_colar(r: dict, formato: str, capitulos=None) -> dict:
    """Título, legenda e hashtags separados, para o painel mostrar com botão Copiar."""
    try:
        import publicar_youtube
        desc_yt = publicar_youtube.descricao(r, formato, capitulos)
    except Exception:
        desc_yt = f"{r.get('descricao', '')}\n\n{' '.join(r.get('hashtags', []))}".strip()
    return {
        "titulo_youtube": r["titulo"],
        "descricao_youtube": desc_yt,
        "legenda_tiktok": r.get("legenda_tiktok") or r["titulo"],
        "hashtags_tiktok": " ".join(r.get("hashtags_tiktok") or r.get("hashtags", [])),
        "tags_youtube": ", ".join(r.get("tags_youtube", [])),
    }


def roteiro_da_chamada(r: dict, url_longo: str | None) -> dict:
    """Textos do Short que divulga o vídeo longo (link do longo na descrição)."""
    titulo = r.get("titulo_short") or r["titulo"]
    link = url_longo if url_longo and url_longo.startswith("http") else "no canal"
    hashtags = list(r.get("hashtags", []))
    if "#shorts" not in [h.lower() for h in hashtags]:
        hashtags.append("#shorts")
    return {
        "titulo": titulo[:95], "assunto": r.get("assunto", ""),
        "descricao_pronta": f"{r['titulo']}\n\n▶ VÍDEO COMPLETO: {link}\n\n{' '.join(hashtags)}",
        "legenda_tiktok": f"{titulo} 👀\nO vídeo completo está no nosso YouTube!",
        "hashtags_tiktok": r.get("hashtags_tiktok", []), "hashtags": hashtags,
        "tags_youtube": r.get("tags_youtube", []), "url_longo": url_longo,
    }


def textos_da_chamada(rc: dict) -> dict:
    return {
        "titulo_youtube": rc["titulo"], "descricao_youtube": rc["descricao_pronta"],
        "legenda_tiktok": rc["legenda_tiktok"], "hashtags_tiktok": " ".join(rc["hashtags_tiktok"]),
        "tags_youtube": ", ".join(rc["tags_youtube"]),
    }


PASTA_CELULAR = config.PASTA / "docs" / "tiktok"  # cópia leve dos Shorts, servida pelo próprio painel


def copia_para_celular(arquivo, nome: str, manter: int = 6) -> str | None:
    """Cópia leve (720p) do Short dentro do painel: no celular, o botão "Mandar pro TikTok" passa esse
    arquivo direto para o app do TikTok (o link do GitHub não deixa o navegador pegar o arquivo)."""
    import subprocess
    try:
        PASTA_CELULAR.mkdir(parents=True, exist_ok=True)
        destino = PASTA_CELULAR / f"{nome}.mp4"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(arquivo),
                        "-vf", "scale=720:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(destino)],
                       check=True, timeout=600)
        for velho in sorted(PASTA_CELULAR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)[:-manter]:
            velho.unlink()  # só os mais recentes ficam no painel (os outros continuam no GitHub)
        return f"tiktok/{destino.name}"
    except Exception as erro:
        print(f"   (não consegui fazer a cópia para o celular: {erro})")
        return None


def _automatico() -> bool:
    return os.getenv("GITHUB_EVENT_NAME") == "schedule" or os.getenv("AGENDADO") == "sim"


def _registrar_no_painel(r: dict, resultados: dict, mp4: str | None, segundos: float,
                         formato: str = "curto", capa: str | None = None, capitulos=None,
                         textos: dict | None = None, extra: dict | None = None):
    """Adiciona o vídeo em docs/videos.json, que o painel (GitHub Pages) mostra."""
    arquivo = config.PASTA / "docs" / "videos.json"
    if not arquivo.parent.exists():
        return
    try:
        lista = json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        lista = []
    item = {"data": datetime.now().astimezone().isoformat(timespec="seconds"),
            "titulo": r["titulo"], "assunto": r.get("assunto", ""),
            "legenda": _legenda(r), "segundos": round(segundos), "formato": formato,
            "textos": textos or _textos_para_colar(r, formato, capitulos), **(extra or {}), **resultados}
    if r.get("tendencia"):
        item["tendencia"] = r["tendencia"]
    if not _automatico():
        item["manual"] = True  # pedido à mão: não conta como o vídeo do horário automático
    if r.get("_tag") and "id" not in item:
        item["id"] = r["_tag"]
    if mp4:
        item["mp4"] = mp4
    if capa:
        item["capa"] = capa
    if os.getenv("GITHUB_RUN_ID"):
        item["execucao"] = (f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}"
                            f"/actions/runs/{os.getenv('GITHUB_RUN_ID')}")
    lista.append(item)
    arquivo.write_text(json.dumps(lista[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def _status_no_painel(**redes):
    painel = config.PASTA / "docs" / "config.json"
    if not painel.exists():
        return
    cfg = json.loads(painel.read_text(encoding="utf-8"))
    for rede, ok in redes.items():
        cfg[f"{rede}_conectado"] = bool(ok)
    painel.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tema", help="assunto específico para este vídeo")
    ap.add_argument("--formato", choices=["curto", "longo"], default=os.getenv("FORMATO") or "curto",
                    help="curto = vertical (TikTok/Shorts) · longo = horizontal (YouTube)")
    ap.add_argument("--sem-publicar", action="store_true", help="só gera o vídeo")
    ap.add_argument("--manter-arquivos", action="store_true", help="não apaga clipes e cenas intermediárias")
    args = ap.parse_args()
    longo = args.formato == "longo"

    # horário automático: se já saiu um vídeo desse formato hoje (ex.: o agendamento do GitHub
    # atrasou e alguém já gerou na mão), não repete
    if _automatico():
        try:
            hoje = datetime.now().astimezone().date().isoformat()
            lista = json.loads((config.PASTA / "docs" / "videos.json").read_text(encoding="utf-8"))
            if any(v.get("formato") == args.formato and not v.get("chamada_de") and not v.get("manual")
                   and str(v.get("data", "")).startswith(hoje) for v in lista):
                print(f"⏭️  Já tem vídeo {args.formato} de hoje no painel; o horário automático não vai repetir.")
                return
        except Exception:
            pass

    historico = _historico()
    tema = args.tema or (None if longo else _proximo_tema_da_lista())
    tendencia = None
    if not tema:  # automático: parte do que está em alta hoje no Brasil
        print("📈 Olhando o que está em alta hoje (Google Trends + YouTube)...")
        try:
            import tendencias
            escolha = tendencias.escolher_tema(args.formato, historico, evitar=historico[-1] if historico else "")
            if escolha:
                tema = tendencias.tema_com_contexto(escolha)
                tendencia = escolha.get("tendencia")
        except Exception:
            traceback.print_exc()

    print(f"🧠 Escrevendo o roteiro ({args.formato})...")
    r = gerador_roteiro.gerar_longo(tema, historico) if longo else gerador_roteiro.gerar(tema, historico)
    r = gerador_roteiro.textos_virais(r, args.formato, tema)
    if gerador_roteiro.modo_noticia(tema):  # notícia sobre pessoas reais: confere tudo com os fatos do pedido
        try:
            r = gerador_roteiro.revisar_noticia(r, tema)
        except RuntimeError as erro:
            if args.tema:  # pedido feito à mão: não publica e avisa
                raise
            # horário automático: em vez de ficar sem vídeo, troca por um mistério forte
            print(f"::warning title=Notícia descartada::{erro} Trocando por um tema de mistério.")
            tema, tendencia = None, None
            r = gerador_roteiro.gerar_longo(None, historico) if longo else gerador_roteiro.gerar(None, historico)
            r = gerador_roteiro.textos_virais(r, args.formato, None)
    r = gerador_roteiro.revisar_cenas(r)  # cada foto tem que mostrar o que está sendo dito naquele trecho
    if gerador_roteiro.modo_noticia(tema):
        r["so_fotos_reais"] = True  # notícia: só fotos reais do assunto, nada de imagem genérica
    if tema and "MÚSICA DE PERIGO" in tema.upper():
        r["musica"] = "perigo"  # trilha de suspense feita na hora (video._trilha_perigo)
    if tendencia:
        r["tendencia"] = tendencia
    print(f"   → {r['titulo']}")

    pasta = config.PASTA_SAIDA / f"{datetime.now():%Y-%m-%d_%H%M}_{_slug(r['assunto'])}"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "roteiro.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    print("🎙️  Gravando a narração...")
    audio = pasta / "narracao.mp3"
    inicios = None
    if longo:
        palavras, inicios = voz.gerar_partes([p["texto"] for p in r["partes"]], audio)
    else:
        palavras = voz.gerar(r["roteiro"], audio)

    final = video.montar(r, audio, palavras, pasta, formato=args.formato, inicios_partes=inicios)
    if video.CREDITOS:  # licença das fotos da Wikimedia pede crédito
        creditos = "\n".join(f"• {c}" for c in dict.fromkeys(video.CREDITOS))
        r["descricao"] = f"{r.get('descricao', '').strip()}\n\n📷 Fotos (Wikimedia Commons):\n{creditos}"
    destino = pasta / f"{_slug(r['titulo'])}.mp4"
    final.rename(destino)
    segundos = video.duracao(destino)
    print(f"✅ Vídeo pronto: {destino} ({segundos / 60:.1f} min)")

    capa, capitulos, chamada = None, None, None
    if longo:
        capa = video.criar_capa(destino, r.get("texto_capa") or r["titulo"],
                                pasta / f"{_slug(r['titulo'])}-capa.jpg",
                                prompt_ia=r.get("prompt_capa") or r.get("assunto"))
        capitulos = [(t, p["titulo"]) for t, p in zip(inicios, r["partes"])]
        try:
            print("✂️  Criando o Short de chamada para o vídeo longo...")
            chamada = video.criar_chamada(destino, r.get("titulo_short") or r["titulo"],
                                          pasta / f"{_slug(r['titulo'])}-short.mp4")
        except Exception:
            traceback.print_exc()
            print("::warning title=Short::Não consegui criar o Short de chamada; o vídeo longo segue normal.")
    mp4, capa_url = _preparar_download(r, destino, capa, [chamada] if chamada else [])
    chamada_url = _url_release(r["_tag"], chamada) if chamada and r.get("_tag") else None
    nome = r.get("_tag") or _slug(r["titulo"])
    celular = None if longo else copia_para_celular(destino, nome)
    celular_chamada = copia_para_celular(chamada, f"{nome}-short") if chamada else None

    if not args.manter_arquivos:
        for lixo in list(pasta.glob("clipe_*.mp4")) + list(pasta.glob("cena_*.mp4")) + [pasta / "cenas.txt"]:
            lixo.unlink(missing_ok=True)

    historico.append(r["assunto"])
    _salvar_historico(historico)

    def registrar(resultados_longo: dict, resultados_chamada: dict):
        _registrar_no_painel(r, resultados_longo, mp4, segundos, args.formato, capa_url, capitulos,
                             extra={"celular": celular} if celular else None)
        if chamada:
            rc = roteiro_da_chamada(r, resultados_longo.get("youtube"))
            extra = {"chamada_de": r.get("_tag"), "id": f"{r.get('_tag')}-short"}
            if celular_chamada:
                extra["celular"] = celular_chamada
            _registrar_no_painel({**rc, "_tag": None}, resultados_chamada, chamada_url,
                                 video.duracao(chamada), "curto", None, None, textos_da_chamada(rc), extra)

    if args.sem_publicar:
        registrar({}, {})
        return

    import tiktok_token
    import youtube_token
    redes = [("youtube", config.PUBLICAR_YOUTUBE, youtube_token.conectado())]
    if not longo:  # vídeo horizontal longo não combina com TikTok
        redes.append(("tiktok", config.PUBLICAR_TIKTOK, tiktok_token.conectado()))
    _status_no_painel(youtube=youtube_token.conectado(), tiktok=tiktok_token.conectado())

    resultados, falhou = {}, False
    for nome, ligado, conectado in redes:
        if not ligado:
            continue
        if not conectado:
            print(f"⏭️  {nome}: ainda não conectado, pulando (o vídeo fica para download no painel).")
            continue
        print(f"📤 Publicando no {nome}...")
        try:
            if nome == "youtube":
                import publicar_youtube
                resultados[nome] = publicar_youtube.publicar(destino, r, args.formato, capitulos, capa)
            else:
                import publicar_tiktok
                try:
                    resultados[nome] = publicar_tiktok.publicar(destino, r)
                except Exception:
                    print("   TikTok não respondeu, tentando de novo em 30 s...")
                    import time
                    time.sleep(30)
                    resultados[nome] = publicar_tiktok.publicar(destino, r)
        except Exception:
            resultados[nome] = "ERRO"
            traceback.print_exc()
            if nome == "youtube":
                falhou = True
            else:  # TikTok é opcional: o vídeo continua no painel para postar à mão
                print(f"::warning title={nome}::Não consegui mandar para o {nome}; use Baixar + Copiar no painel.")

    # Short de chamada → YouTube, com o link do vídeo longo na descrição
    resultados_chamada = {}
    url_longo = resultados.get("youtube")
    if chamada and url_longo and url_longo != "ERRO":
        print("📤 Publicando o Short de chamada no YouTube...")
        try:
            import publicar_youtube
            resultados_chamada["youtube"] = publicar_youtube.publicar(
                chamada, roteiro_da_chamada(r, url_longo), "curto")
        except Exception:
            resultados_chamada["youtube"] = "ERRO"
            traceback.print_exc()

    (pasta / "publicacao.json").write_text(json.dumps({**resultados, "short": resultados_chamada},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    for rede, res in resultados.items():
        print(f"   {rede}: {res}")
    registrar(resultados, resultados_chamada)
    if falhou:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
