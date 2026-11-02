"""O que está em alta HOJE no Brasil (Google Trends + YouTube em alta) e escolha do tema do vídeo.

O vídeo automático usa a tendência como gancho e aprofunda o assunto com fatos conhecidos,
apoiado nas manchetes do dia (para não inventar detalhes do acontecimento).
"""
import json
import re
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
NOTICIAS_MISTERIO = [  # notícias recentes nos 4 focos do canal: política, lugares, assombrações e alienígenas
    _GN + "Lula+OR+Congresso+OR+STF+OR+Trump+OR+%22Casa+Branca%22+OR+elei%C3%A7%C3%A3o+OR+Planalto+when:1d",
    _GN + "%22pol%C3%ADtica+internacional%22+OR+%22crise+diplom%C3%A1tica%22+OR+presidente+OR+%22primeiro-ministro%22+when:1d",
    _GN + "mal-assombrado+OR+assombra%C3%A7%C3%A3o+OR+fantasma+OR+%22casa+assombrada%22+OR+%22lugar+abandonado%22+when:7d",
    _GN + "OVNI+OR+UAP+OR+extraterrestre+OR+alien%C3%ADgena+OR+%22vida+fora+da+Terra%22+OR+%22objeto+voador%22+when:7d",
    _GN + "%22cidade+abandonada%22+OR+%22cidade+fantasma%22+OR+%22ilha+proibida%22+OR+%22lugar+misterioso%22+OR+%22lugar+proibido%22+when:7d",
    _GN + "mist%C3%A9rio+OR+enigma+OR+inexplic%C3%A1vel+OR+%22sem+explica%C3%A7%C3%A3o%22+OR+arque%C3%B3logos+when:3d",
]

# palavras de notícia com vítima/tragédia/crime: essas tendências NUNCA viram vídeo
TRAGEDIA = ("morre", "morreu", "morte", "mortes", "morto", "mortos", "morta", "mata ", "matou", "vítima", "vitima",
            "assassin", "homicíd", "tragédia", "tragedia", "acidente", "ferido", "feridos", "desaparecid", "velório",
            "enterro", "luto", "estupr", "sequestr", "baleado", "tiroteio", "crime", "preso ", "presa ", "suicíd",
            "afogad", "atropel", "facada", "esfaque", "corpo encontrado", "óbito", "falece", "chacina", "violência")


# morte de famoso por causa natural pode virar HOMENAGEM; estas palavras indicam morte violenta, crime,
# acidente ou suicídio, e aí nunca vira vídeo
VIOLENTO = ("mata ", "matou", "assassin", "homicíd", "acidente", "ferido", "feridos", "desaparecid", "estupr",
            "sequestr", "baleado", "tiroteio", "crime", "preso ", "presa ", "suicíd", "afogad", "atropel", "facada",
            "esfaque", "corpo encontrado", "chacina", "violência", "overdose", "vítimas", "tragédia", "tragedia",
            "queda de avião", "incêndio", "desabamento", "enchente", "deslizamento")


def _tragico(*textos) -> bool:
    t = " ".join(str(x) for x in textos).lower() + " "
    return any(p in t for p in TRAGEDIA)


def _violento(*textos) -> bool:
    t = " ".join(str(x) for x in textos).lower() + " "
    return any(p in t for p in VIOLENTO)


def _sem_violencia(*textos) -> bool:
    """Passa no filtro de entrada: tragédia com violência nunca; morte simples fica para a IA avaliar homenagem."""
    return not _violento(*textos)


def noticias_de_misterio(limite: int = 40) -> list[str]:
    """Manchetes recentes (3 dias) de descobertas, mistérios e ciência no Google Notícias Brasil."""
    titulos = []
    for url in NOTICIAS_MISTERIO:
        try:
            r = requests.get(url, headers=CAB, timeout=30)
            r.raise_for_status()
            titulos += [(i.findtext("title") or "").strip() for i in ET.fromstring(r.content).iter("item")][:8]
        except Exception as erro:
            print(f"   Google Notícias indisponível ({erro})")
    return [t for t in dict.fromkeys(titulos) if t and _sem_violencia(t)][:limite]


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

Notícias recentes de política, lugares curiosos, assombrações e OVNIs (PREFIRA estas, são o assunto do canal):
{noticias}

Temas que o canal JÁ fez (não repita): {usados}
{evitar}

FOCO DO CANAL (o dono pediu): escolha SEMPRE dentro destes 4 assuntos, nesta ordem de preferência:
  1) POLÍTICA em alta (Brasil e mundo) que todo mundo está comentando → "tipo": "noticia", jornalístico e neutro;
  2) CURIOSIDADES DE LUGARES (lugares proibidos, ilhas, cidades abandonadas, construções misteriosas);
  3) LUGARES ASSOMBRADOS e lendas de assombração com história documentada;
  4) CONTATO ALIENÍGENA, OVNIs e casos investigados.
Animais, cogumelos, saúde e ciência em geral só entram se nada desses 4 estiver em alta hoje.

Escolha UMA tendência de hoje e transforme num vídeo do nicho do canal, aprofundando o assunto:
use a tendência como gancho e desenvolva com o lado curioso/misterioso e com fatos históricos ou
científicos bem conhecidos relacionados a ela (ex.: em alta "eclipse" → "o mistério dos eclipses que
assustaram reis"; em alta um filme de terror → "o caso real que inspirou o filme").

Regras:
- A ligação entre a tendência e o tema tem que ser REAL e direta (o vídeo fala do mesmo assunto da tendência),
  nunca uma associação forçada. Ex. ruim: em alta "operadora fechou acordo com Starlink" → "sinais misteriosos
  captados pela Starlink" (isso é inventado). Se a ligação for fraca, responda {{"tema": ""}}.
- Nunca atribua mistérios, descobertas ou acontecimentos a empresas, marcas ou pessoas reais.
- Prefira tendências que rendem curiosidade ou mistério; evite futebol puro, ofertas e loterias.
- NUNCA transforme em "mistério" assuntos do dia a dia: falta de luz/água/internet, chuva e previsão do tempo,
  trânsito, preços, salário, INSS, Pix, concursos, programas de TV. Isso não é curiosidade, é serviço.
- PROIBIDO: qualquer notícia com mortos, feridos, vítimas, acidentes, crimes, desastres ou luto (ex.: "casal morre
  atingido por raio" NÃO serve, nem com outro ângulo), saúde de pessoas reais, menores de idade, pessoas comuns
  (não famosas), vida sexual, traição ou boato sem fonte.
- MORTE DE FAMOSO (artista, atleta, figura pública) confirmada nas manchetes VALE como homenagem, contando a
  história e as conquistas dele: marque "tipo": "homenagem". NÃO vale se foi morte violenta, crime, acidente,
  suicídio ou overdose, nem para vítimas de desastres.
- FOFOCA de famosos que todo mundo está comentando VALE, se estiver nas manchetes de veículos conhecidos
  (ex.: término, casamento, briga pública, polêmica, revelação de um famoso): marque "tipo": "noticia"; o vídeo
  conta só o que as manchetes dizem, com "segundo", sem julgar nem inventar detalhes.
- Política: prioridade do canal. Escolha o assunto político que mais está bombando hoje e marque "tipo": "noticia";
  o vídeo vai ser jornalístico e neutro, só com o que está nas manchetes, com "segundo", sem acusar ninguém
  e sem tomar lado.
- Descobertas da ciência e da medicina (novo tratamento, vacina, terapia, estudo surpreendente) são ótimas: marque
  "tipo": "noticia". Nada de "cura milagrosa" ou promessa; o vídeo diz em que fase está a pesquisa.
- Prefira as notícias de mistério/descoberta/ciência acima; das buscas do Google use só as que já são curiosidade
  (fenômeno no céu, descoberta, lugar misterioso, filme/série de mistério).
- Sobre o acontecimento de hoje, só afirme o que está nas manchetes; o resto do vídeo é aprofundamento com fatos conhecidos.
- Se nenhuma tendência servir, responda {{"tema": ""}}.

- Dê uma nota de 0 a 10 para o quanto o tema desperta CURIOSIDADE (vontade de assistir até o fim para saber
  a resposta). Notícia comum, esporte ou economia = nota baixa; fofoca bombando com fonte pode ter nota alta. Só sugira temas com nota 8 ou mais;
  senão responda {{"tema": ""}}.

Responda SOMENTE com JSON:
{{"curiosidade": 0, "tipo": "curiosidade, noticia ou homenagem", "tendencia": "a busca/vídeo em alta escolhido", "tema": "tema do vídeo, específico e curioso (até 90 caracteres)",
  "angulo": "1 frase: como ligar a tendência ao nicho", "manchetes": ["manchetes de hoje que embasam o gancho"]}}"""


_COMUNS = {"misterio", "misterios", "segredo", "segredos", "verdade", "historia", "historias", "descoberta",
           "descobertas", "cientistas", "pesquisadores", "brasil", "brasileiro", "brasileira", "mundo", "curiosidade",
           "curiosidades", "estranho", "incrivel", "revela", "revelado", "realmente", "pode", "podem", "sobre",
           "ainda", "nunca", "antigo", "antiga", "novo", "nova", "ciencia", "caso", "casos", "anos"}


def _palavras(texto: str) -> set[str]:
    """Palavras importantes de um tema (sem acento, sem plural, sem palavras genéricas)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    saida = set()
    for p in re.findall(r"[a-z]{5,}", t):
        p = p[:-1] if p.endswith("s") else p
        if p not in _COMUNS and p + "s" not in _COMUNS:
            saida.add(p)
    return saida


def _repetido(dados: dict, usados: list[str], ultimos: int = 12) -> str | None:
    """Devolve o tema recente parecido (mesma palavra-chave), se houver — ex.: 'cogumelo' três dias seguidos."""
    novo = _palavras(f"{dados.get('tema', '')} {dados.get('tendencia', '')}")
    for antigo in usados[-ultimos:]:
        comum = novo & _palavras(antigo)
        if comum:
            return f"{antigo} (palavra repetida: {', '.join(sorted(comum))})"
    return None


def escolher_tema(formato: str, usados: list[str], evitar: str = "") -> dict | None:
    """Escolhe o tema do dia a partir das tendências. Retorna {'tema','tendencia','angulo','manchetes'} ou None."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        return None
    google = [g for g in google_trends() if _sem_violencia(g["busca"], *g["manchetes"])]
    youtube = [t for t in youtube_em_alta() if _sem_violencia(t)]
    noticias = noticias_de_misterio()
    if not google and not youtube and not noticias:
        print("   ⚠️ não consegui ler as tendências de hoje; a IA escolhe o tema sozinha.")
        return None
    linhas_google = "\n".join(
        f"- {g['busca']} ({g['volume']} buscas)" + (": " + " | ".join(g["manchetes"]) if g["manchetes"] else "")
        for g in google) or "(indisponível)"
    import roteiro
    pedir = roteiro._pedir_ao_groq if config.GROQ_API_KEY else roteiro._pedir_ao_gemini
    proibidos = [evitar] if evitar else []
    for tentativa in range(3):  # o tema não pode repetir assunto dos últimos vídeos (a IA às vezes ignora a lista)
        try:
            dados = pedir(PROMPT.format(
                nicho=config.NICHO,
                formato="Short de 1 minuto" if formato == "curto" else "vídeo longo de ~8 minutos com capítulos",
                google=linhas_google, youtube="\n".join(f"- {t}" for t in youtube) or "(indisponível)",
                noticias="\n".join(f"- {t}" for t in noticias) or "(indisponível)",
                usados=", ".join(usados[-60:]) or "nenhum",
                evitar=("Não use estes assuntos de jeito nenhum (já viraram vídeo nos últimos dias): "
                        + " | ".join(proibidos)) if proibidos else "",
            ))
        except Exception as erro:
            print(f"   ⚠️ não consegui escolher pela tendência ({erro})")
            return None
        parecido = _repetido(dados, usados)
        if not parecido:
            break
        print(f"   🔁 '{dados.get('tema')}' repete um vídeo recente: {parecido}. Escolhendo outro...")
        proibidos.append(str(dados.get("tendencia") or dados.get("tema")))
    else:
        print("   as tendências de hoje repetem assuntos recentes; a IA escolhe um mistério novo.")
        return None
    if not str(dados.get("tema", "")).strip():
        print("   nenhuma tendência de hoje combinou com o canal; a IA escolhe o tema sozinha.")
        return None
    try:
        nota = float(dados.get("curiosidade", 0))
    except (TypeError, ValueError):
        nota = 0
    homenagem = str(dados.get("tipo", "")).lower().startswith("homen")
    noticia = homenagem or str(dados.get("tipo", "")).lower().startswith("not")
    if noticia and not dados.get("manchetes"):
        print("   notícia sem manchetes para conferir; a IA escolhe um mistério forte.")
        return None
    cotidiano = r"apag[ãa]o|falta de (luz|energia|[áa]gua)|energia el[ée]trica|previs[ãa]o do tempo|chuva|temporal|" \
                r"tr[âa]nsito|pre[çc]o|sal[áa]rio|inss|pix|concurso|enem|loteria|mega-sena"
    if re.search(cotidiano, f"{dados.get('tendencia', '')} {dados.get('tema', '')}", re.I):
        print(f"   '{dados.get('tema')}' é assunto do dia a dia, não curiosidade; a IA escolhe um mistério forte.")
        return None
    if nota < (7 if noticia else 9):
        print(f"   '{dados.get('tema')}' tem pouca curiosidade (nota {nota}); a IA escolhe um mistério forte.")
        return None
    tudo = (dados.get("tendencia"), dados.get("tema"), dados.get("angulo"), *dados.get("manchetes", []))
    if homenagem and _violento(*tudo):
        print(f"   🚫 '{dados.get('tendencia')}': morte violenta, acidente ou crime não vira homenagem.")
        return None
    if not homenagem and _tragico(*tudo):
        print(f"   🚫 '{dados.get('tendencia')}' envolve tragédia/vítimas; a IA escolhe um mistério clássico.")
        return None
    dados["manchetes"] = [str(m) for m in dados.get("manchetes", []) if str(m).strip()][:4]
    print(f"   📈 em alta: {dados.get('tendencia')} → tema: {dados['tema']}")
    return dados


def tema_com_contexto(escolha: dict) -> str:
    """Texto do tema que vai para o roteirista, com o gancho de hoje e as manchetes como base."""
    homenagem = str(escolha.get("tipo", "")).lower().startswith("homen")
    noticia = homenagem or str(escolha.get("tipo", "")).lower().startswith("not")
    partes = [escolha["tema"]]
    if homenagem:
        partes.append("HOMENAGEM, tom respeitoso e emocionante: conte a trajetória, as obras e as conquistas da "
                      "pessoa (fatos públicos e amplamente conhecidos da carreira podem ser usados). Sobre a morte, "
                      "só diga o que está nas manchetes (data e idade); a causa só se for natural e estiver nas "
                      "manchetes, sem detalhes. Nada de sensacionalismo, 'mistério' ou especulação. Termine com uma "
                      "mensagem de homenagem e peça para o público deixar uma lembrança nos comentários.")
    if noticia and re.search(r"tratament|vacina|terapia|medic|doen|c[âa]ncer|sa[úu]de|rem[ée]dio|cura|estudo", " ".join(
            [escolha.get("tema", ""), escolha.get("tendencia", "") or "", *escolha.get("manchetes", [])]), re.I):
        partes.append("SAÚDE: diga em que fase está (estudo em laboratório, em animais, testes em pessoas ou já "
                      "aprovado), quem pesquisou e que ainda não é cura garantida se não for; nunca indique remédio, "
                      "dose ou que alguém pare um tratamento; termine lembrando que a pessoa deve falar com um médico.")
    if noticia:  # ativa o modo notícia do roteiro: título neutro + checagem de fatos com as manchetes
        partes.insert(0, "NOTÍCIA DO DIA, tom jornalístico neutro, sem acusar ninguém e sem afirmar o que não está "
                         "nas manchetes; use 'segundo' e 'teria' para o que não é confirmado; não cite porcentagens "
                         "que não estejam nas manchetes. FATOS:")
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
