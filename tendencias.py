"""O que está em alta HOJE no Brasil (Google Trends + YouTube em alta) e escolha do tema do vídeo.

O vídeo automático usa a tendência como gancho e aprofunda o assunto com fatos conhecidos,
apoiado nas manchetes do dia (para não inventar detalhes do acontecimento).
"""
import json
import xml.etree.ElementTree as ET

import requests

import config

NS = {"ht": "https://trends.google.com/trending/rss"}
FONTES_TRENDS = [
    "https://trends.google.com/trending/rss?geo=BR",
    "https://trends.google.com.br/trending/rss?geo=BR",
]
CAB = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def google_trends(limite: int = 25) -> list[dict]:
    """Buscas em alta no Google Brasil: [{'busca', 'volume', 'manchetes': [...]}]."""
    for url in FONTES_TRENDS:
        try:
            r = requests.get(url, headers=CAB, timeout=30)
            r.raise_for_status()
            raiz = ET.fromstring(r.content)
        except Exception as erro:
            print(f"   Google Trends indisponível em {url} ({erro})")
            continue
        itens = []
        for item in raiz.iter("item"):
            titulo = (item.findtext("title") or "").strip()
            if not titulo:
                continue
            manchetes = []
            for n in item.findall("ht:news_item", NS):
                t = (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip()
                fonte = (n.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip()
                if t:
                    manchetes.append(f"{t} ({fonte})" if fonte else t)
            itens.append({"busca": titulo, "volume": (item.findtext("ht:approx_traffic", default="", namespaces=NS) or "").strip(),
                          "manchetes": manchetes[:3]})
            if len(itens) >= limite:
                break
        if itens:
            return itens
    return []


_GN = "https://news.google.com/rss/search?hl=pt-BR&gl=BR&ceid=BR:pt-419&q="
NOTICIAS_MISTERIO = [  # notícias dos últimos 3 dias que já nascem curiosas
    _GN + "mist%C3%A9rio+OR+enigma+OR+inexplic%C3%A1vel+OR+%22sem+explica%C3%A7%C3%A3o%22+when:3d",
    _GN + "mal-assombrado+OR+assombra%C3%A7%C3%A3o+OR+fantasma+OR+%22lugar+abandonado%22+when:3d",
    _GN + "arque%C3%B3logos+OR+%22descoberta+rara%22+OR+%22cientistas+descobrem%22+OR+f%C3%B3ssil+when:3d",
    _GN + "OVNI+OR+%22fen%C3%B4meno+estranho%22+OR+%22luzes+no+c%C3%A9u%22+OR+NASA+when:3d",
]

# palavras de notícia com vítima/tragédia/crime: essas tendências NUNCA viram vídeo
TRAGEDIA = ("morre", "morreu", "morte", "mortes", "morto", "mortos", "morta", "mata ", "matou", "vítima", "vitima",
            "assassin", "homicíd", "tragédia", "tragedia", "acidente", "ferido", "feridos", "desaparecid", "velório",
            "enterro", "luto", "estupr", "sequestr", "baleado", "tiroteio", "crime", "preso ", "presa ", "suicíd",
            "afogad", "atropel", "facada", "esfaque", "corpo encontrado", "óbito", "falece", "chacina", "violência")


def _tragico(*textos) -> bool:
    t = " ".join(str(x) for x in textos).lower() + " "
    return any(p in t for p in TRAGEDIA)


def noticias_de_misterio(limite: int = 20) -> list[str]:
    """Manchetes recentes (3 dias) de descobertas, mistérios e ciência no Google Notícias Brasil."""
    titulos = []
    for url in NOTICIAS_MISTERIO:
        try:
            r = requests.get(url, headers=CAB, timeout=30)
            r.raise_for_status()
            titulos += [(i.findtext("title") or "").strip() for i in ET.fromstring(r.content).iter("item")][:8]
        except Exception as erro:
            print(f"   Google Notícias indisponível ({erro})")
    return [t for t in dict.fromkeys(titulos) if t and not _tragico(t)][:limite]


def youtube_em_alta(limite: int = 25) -> list[str]:
    """Títulos dos vídeos em alta no YouTube Brasil (usa a conexão do canal; custa 1 unidade de cota)."""
    try:
        import youtube_token
        if not youtube_token.conectado():
            return []
        from googleapiclient.discovery import build
        import publicar_youtube
        yt = build("youtube", "v3", credentials=publicar_youtube._credenciais(), cache_discovery=False)
        resp = yt.videos().list(part="snippet", chart="mostPopular", regionCode="BR", maxResults=limite).execute()
        return [i["snippet"]["title"] for i in resp.get("items", [])]
    except Exception as erro:
        print(f"   YouTube em alta indisponível ({erro})")
        return []


PROMPT = """Você é o editor de pauta de um canal brasileiro de YouTube/TikTok.
Nicho do canal: {nicho}
Formato do próximo vídeo: {formato}

O QUE ESTÁ EM ALTA HOJE NO BRASIL
Buscas em alta no Google (com manchetes do dia):
{google}

Vídeos em alta no YouTube Brasil:
{youtube}

Notícias recentes de mistérios, descobertas e ciência (PREFIRA estas, são o assunto do canal):
{noticias}

Temas que o canal JÁ fez (não repita): {usados}
{evitar}

Escolha UMA tendência de hoje e transforme num vídeo do nicho do canal, aprofundando o assunto:
use a tendência como gancho e desenvolva com o lado curioso/misterioso e com fatos históricos ou
científicos bem conhecidos relacionados a ela (ex.: em alta "eclipse" → "o mistério dos eclipses que
assustaram reis"; em alta um filme de terror → "o caso real que inspirou o filme").

Regras:
- A ligação entre a tendência e o tema tem que ser REAL e direta (o vídeo fala do mesmo assunto da tendência),
  nunca uma associação forçada. Ex. ruim: em alta "operadora fechou acordo com Starlink" → "sinais misteriosos
  captados pela Starlink" (isso é inventado). Se a ligação for fraca, responda {{"tema": ""}}.
- Nunca atribua mistérios, descobertas ou acontecimentos a empresas, marcas ou pessoas reais.
- Prefira tendências que rendem curiosidade ou mistério; evite fofoca, futebol puro, ofertas e loterias.
- PROIBIDO: qualquer notícia com mortos, feridos, vítimas, acidentes, crimes, desastres ou luto (ex.: "casal morre
  atingido por raio" NÃO serve, nem com outro ângulo), saúde de pessoas reais, eleição/política partidária.
- Prefira as notícias de mistério/descoberta/ciência acima; das buscas do Google use só as que já são curiosidade
  (fenômeno no céu, descoberta, lugar misterioso, filme/série de mistério).
- Sobre o acontecimento de hoje, só afirme o que está nas manchetes; o resto do vídeo é aprofundamento com fatos conhecidos.
- Se nenhuma tendência servir, responda {{"tema": ""}}.

- Dê uma nota de 0 a 10 para o quanto o tema desperta CURIOSIDADE (vontade de assistir até o fim para saber
  a resposta). Notícia comum, esporte, economia ou celebridade = nota baixa. Só sugira temas com nota 8 ou mais;
  senão responda {{"tema": ""}}.

Responda SOMENTE com JSON:
{{"curiosidade": 0, "tendencia": "a busca/vídeo em alta escolhido", "tema": "tema do vídeo, específico e curioso (até 90 caracteres)",
  "angulo": "1 frase: como ligar a tendência ao nicho", "manchetes": ["manchetes de hoje que embasam o gancho"]}}"""


def escolher_tema(formato: str, usados: list[str], evitar: str = "") -> dict | None:
    """Escolhe o tema do dia a partir das tendências. Retorna {'tema','tendencia','angulo','manchetes'} ou None."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        return None
    google = [g for g in google_trends() if not _tragico(g["busca"], *g["manchetes"])]
    youtube = [t for t in youtube_em_alta() if not _tragico(t)]
    noticias = noticias_de_misterio()
    if not google and not youtube and not noticias:
        print("   ⚠️ não consegui ler as tendências de hoje; a IA escolhe o tema sozinha.")
        return None
    linhas_google = "\n".join(
        f"- {g['busca']} ({g['volume']} buscas)" + (": " + " | ".join(g["manchetes"]) if g["manchetes"] else "")
        for g in google) or "(indisponível)"
    import roteiro
    pedir = roteiro._pedir_ao_groq if config.GROQ_API_KEY else roteiro._pedir_ao_gemini
    try:
        dados = pedir(PROMPT.format(
            nicho=config.NICHO,
            formato="Short de 1 minuto" if formato == "curto" else "vídeo longo de ~8 minutos com capítulos",
            google=linhas_google, youtube="\n".join(f"- {t}" for t in youtube) or "(indisponível)",
            noticias="\n".join(f"- {t}" for t in noticias) or "(indisponível)",
            usados=", ".join(usados[-60:]) or "nenhum",
            evitar=f"Não use esta tendência (já virou outro vídeo hoje): {evitar}" if evitar else "",
        ))
    except Exception as erro:
        print(f"   ⚠️ não consegui escolher pela tendência ({erro})")
        return None
    if not str(dados.get("tema", "")).strip():
        print("   nenhuma tendência de hoje combinou com o canal; a IA escolhe o tema sozinha.")
        return None
    try:
        nota = float(dados.get("curiosidade", 0))
    except (TypeError, ValueError):
        nota = 0
    if nota < 8:
        print(f"   '{dados.get('tema')}' tem pouca curiosidade (nota {nota}); a IA escolhe um mistério forte.")
        return None
    if _tragico(dados.get("tendencia"), dados.get("tema"), dados.get("angulo"), *dados.get("manchetes", [])):
        print(f"   🚫 '{dados.get('tendencia')}' envolve tragédia/vítimas; a IA escolhe um mistério clássico.")
        return None
    dados["manchetes"] = [str(m) for m in dados.get("manchetes", []) if str(m).strip()][:4]
    print(f"   📈 em alta: {dados.get('tendencia')} → tema: {dados['tema']}")
    return dados


def tema_com_contexto(escolha: dict) -> str:
    """Texto do tema que vai para o roteirista, com o gancho de hoje e as manchetes como base."""
    partes = [escolha["tema"]]
    if escolha.get("tendencia"):
        partes.append(f"GANCHO: isso está em alta hoje no Brasil ({escolha['tendencia']}); comece ligando o vídeo a isso.")
    if escolha.get("angulo"):
        partes.append(f"ÂNGULO: {escolha['angulo']}")
    if escolha.get("manchetes"):
        partes.append("MANCHETES DE HOJE (sobre o acontecimento atual, só afirme o que está aqui): "
                      + " | ".join(escolha["manchetes"]))
    partes.append("Aprofunde com fatos históricos/científicos conhecidos e verificáveis; não invente detalhes.")
    return " ".join(partes)


if __name__ == "__main__":  # teste rápido: python tendencias.py
    print(json.dumps(google_trends(10), ensure_ascii=False, indent=1))
