"""Gera o roteiro do vídeo com a IA do Google (Gemini, plano gratuito)."""
import json
import re
import time

import requests

import config

PROMPT = """Você é roteirista de vídeos curtos virais (YouTube Shorts e TikTok).

Nicho do canal: {nicho}
{tema_linha}
Assuntos que JÁ foram usados (não repita): {usados}

Escreva UM roteiro em {idioma} para narração de cerca de {segundos} segundos
(aproximadamente {palavras} palavras).

Regras do roteiro:
- A primeira frase é um gancho forte que prende nos 2 primeiros segundos.
- Frases curtas e diretas, linguagem falada, sem emojis, sem hashtags, sem "olá pessoal".
- Só fatos verdadeiros e verificáveis. Se não tiver certeza, escolha outro assunto.
- Nunca atribua acontecimentos, descobertas ou falas a empresas, marcas ou pessoas reais se isso não for amplamente conhecido ou não estiver nas manchetes dadas.
- Mistérios: só casos reais e documentados (com lugar, data ou fonte conhecida). Diga com clareza o que é fato comprovado e o que é teoria ou lenda.
- Eleição, política, saúde e notícias: nunca apresente previsão como resultado certo nem invente números; deixe claro que é análise e que pesquisas podem errar.
- Termine com uma frase curta que convide a seguir o canal ou comentar.
- Não escreva indicações de cena, só o texto que será narrado.
- O roteiro PRECISA ter pelo menos {palavras} palavras: desenvolva com 3 a 5 fatos, exemplos e detalhes curiosos.

Responda SOMENTE com um JSON neste formato:
{{
  "assunto": "assunto em poucas palavras",
  "titulo": "título chamativo com até 70 caracteres",
  "roteiro": "texto completo da narração",
  "descricao": "descrição de 2 ou 3 frases para o post",
  "hashtags": ["#exemplo", "#outra", "#shorts"],
  "cenas": ["{cenas} termos de busca EM INGLÊS para vídeos de banco, um por cena, na ordem da narração: o objeto/lugar LITERAL falado naquele trecho (ex: 'radio telescope', 'ancient pyramid'). Se a cena mostra uma PESSOA famosa, LUGAR ou OBJETO real específico, escreva 'wiki:' + nome do artigo da Wikipédia (ex: 'wiki:Pelé', 'wiki:USS Nimitz', 'wiki:Stonehenge'); use SEMPRE o nome COMPLETO do artigo, nunca apelido (ex: 'wiki:Luiz Inácio Lula da Silva', nunca 'wiki:Lula', que é o molusco); não use 'wiki:' para jornais, sites ou empresas. As marcas 'wiki:'/'ia:' vão SÓ aqui em cenas, NUNCA no roteiro falado. Se mostra algo imaginado ou que não existe em vídeo real (ET, nave alienígena, criatura, cena histórica recriada), escreva 'ia:' + descrição visual em inglês (ex: 'ia:grey alien standing in a dark forest at night'). Se o vídeo é sobre ETs, OVNIs, naves ou criaturas, pelo menos METADE das cenas deve ser 'ia:' mostrando o ser/a nave descritos no roteiro, e a cidade/lugar real do caso deve aparecer como 'wiki:' (ex: 'wiki:Varginha'). Lugares mal-assombrados, abandonados ou misteriosos: o lugar real como 'wiki:' (ex: 'wiki:Castelo de Edimburgo', 'wiki:Isla de las Muñecas') e o clima da lenda como 'ia:' (ex: 'ia:dark abandoned hospital corridor with a faint shadow figure'), nunca rosto de pessoa real em 'ia:'. Evite pessoas em escritório, reuniões, finanças e casa"]
}}"""

EXEMPLO = {
    "assunto": "polvos têm três corações",
    "titulo": "O animal que tem TRÊS corações e sangue azul",
    "roteiro": (
        "Existe um animal que tem três corações e sangue azul. "
        "É o polvo. Dois corações bombeiam sangue só para as brânquias, "
        "e o terceiro manda sangue para o resto do corpo. "
        "E o mais curioso: quando o polvo nada, esse terceiro coração simplesmente para de bater. "
        "Por isso ele prefere rastejar, nadar cansa demais. "
        "O sangue é azul por causa da hemocianina, uma proteína com cobre que transporta oxigênio. "
        "E tem mais: dois terços dos neurônios do polvo ficam nos braços, "
        "então cada braço consegue agir quase sozinho. "
        "Segue o canal para mais curiosidades que parecem mentira, mas são verdade."
    ),
    "descricao": "O polvo tem três corações, sangue azul e braços que pensam quase sozinhos. Você sabia?",
    "hashtags": ["#curiosidades", "#polvo", "#natureza", "#vocesabia", "#shorts"],
    "cenas": ["octopus", "octopus swimming", "heart beating", "octopus crawling", "blue water", "octopus tentacles"],
}


def _pedir_ao_gemini(prompt: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODELO}:generateContent"
    )
    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"},
    }
    for tentativa in range(4):
        r = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},  # no cabeçalho: nunca aparece em logs
            json=corpo,
            timeout=90,
        )
        if r.status_code in (429, 500, 503):  # limite do plano grátis / instabilidade
            time.sleep(15 * (tentativa + 1))
            continue
        if r.status_code in (400, 401, 403):
            raise RuntimeError(
                f"Gemini recusou a chave ({r.status_code}). Confira o segredo GEMINI_API_KEY: "
                f"ele deve começar com 'AIza'. Detalhe: {r.text[:300]}"
            )
        r.raise_for_status()
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        texto = re.sub(r"^```(?:json)?|```$", "", texto.strip()).strip()
        return json.loads(texto)
    raise RuntimeError(f"Gemini não respondeu: {r.status_code} {r.text[:300]}")


GROQ_URL = "https://api.groq.com/openai/v1"


def _modelos_groq() -> list[str]:
    r = requests.get(f"{GROQ_URL}/models", headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, timeout=30)
    r.raise_for_status()
    ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    # prefere modelos grandes de texto; ignora voz, visão e moderação
    ruins = ("whisper", "tts", "guard", "vision", "playai", "orpheus", "prompt")
    bons = [i for i in ids if not any(x in i.lower() for x in ruins)]
    preferidos = ("gpt-oss-120b", "llama-3.3-70b", "kimi", "qwen", "llama-4", "gpt-oss")
    return sorted(bons, key=lambda i: next((n for n, p in enumerate(preferidos) if p in i), 99))


def _json_do_texto(texto: str) -> dict:
    """Extrai o JSON da resposta mesmo se vier com texto ou ``` em volta."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        ini, fim = texto.find("{"), texto.rfind("}")
        if ini >= 0 and fim > ini:
            return json.loads(texto[ini:fim + 1])
        raise


def _pedir_ao_groq(prompt: str) -> dict:
    """Groq: plano gratuito em https://console.groq.com/keys (chave começa com gsk_)."""
    candidatos = [config.GROQ_MODELO] if config.GROQ_MODELO else []
    lista_carregada = False
    esperas = 0
    tentativa = 0  # 0-1: modo JSON · 2: texto livre (para respostas longas que o modo JSON recusa)
    ultimo_erro = ""
    while True:
        if not candidatos:
            if lista_carregada:
                raise RuntimeError(f"Nenhum modelo do Groq aceitou o pedido. Último erro: {ultimo_erro}")
            candidatos, lista_carregada = _modelos_groq()[:5], True
            tentativa = 0
        modelo = candidatos[0]
        corpo = {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_completion_tokens": 16000,
        }
        if tentativa < 2:
            corpo["response_format"] = {"type": "json_object"}
        r = requests.post(f"{GROQ_URL}/chat/completions",
                          headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, json=corpo, timeout=180)
        if r.status_code == 429 and esperas < 6:  # limite do plano grátis
            esperas += 1
            time.sleep(20)
            continue
        if r.status_code in (401, 403):
            raise RuntimeError("Groq recusou a chave. Confira o segredo GROQ_API_KEY (começa com 'gsk_').")
        if r.status_code >= 400:
            ultimo_erro = f"{r.status_code} {r.text[:300]}"
            print(f"   ⚠️ Groq ({modelo}) respondeu {ultimo_erro}")
            if r.status_code == 400 and "max_completion_tokens" in r.text and corpo.get("max_completion_tokens", 0) > 8000:
                # modelo com limite menor de resposta: tenta de novo pedindo menos
                corpo_menor = 8000
                r2 = requests.post(f"{GROQ_URL}/chat/completions",
                                   headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                                   json={**corpo, "max_completion_tokens": corpo_menor}, timeout=180)
                if r2.ok:
                    r = r2
            if r.status_code >= 400:
                if r.status_code in (400, 404) and "model" in r.text.lower() and "json" not in r.text.lower():
                    candidatos = candidatos[1:]  # modelo aposentado: tenta o próximo
                elif tentativa < 2:
                    tentativa += 1          # JSON inválido/longo demais: tenta de novo, depois em texto livre
                else:
                    candidatos, tentativa = candidatos[1:], 0
                continue
        try:
            dados = _json_do_texto(r.json()["choices"][0]["message"]["content"] or "")
        except Exception as erro:
            ultimo_erro = f"resposta sem JSON válido ({erro})"
            print(f"   ⚠️ {ultimo_erro}, tentando de novo...")
            if tentativa < 2:
                tentativa += 1
            else:
                candidatos, tentativa = candidatos[1:], 0
            continue
        print(f"   (roteiro escrito pelo modelo {modelo} no Groq)")
        return dados


def limpar_narracao(texto: str) -> str:
    """Tira da fala as marcas de cena ('wiki:Nome', 'ia:descrição') que a IA às vezes mistura na narração."""
    t = str(texto or "")
    # frase que é só a lista de cenas lida em voz alta ("wiki:A, wiki:B, wiki:C..."): sai inteira
    frases = re.split(r"(?<=[.!?\n])", t)
    t = "".join(f for f in frases if len(re.findall(r"\b(?:wiki|ia)\s*:", f, re.I)) < 3)
    t = re.sub(r"\bia\s*:\s*[^,.;!?\n]+", "", t, flags=re.I)  # descrição de imagem em inglês: sai inteira
    t = re.sub(r"\bwiki\s*:\s*", "", t, flags=re.I)              # nome real: fica só o nome
    t = re.sub(r"\s*\((?:Brasil|Brazil|Argentina|EUA|cidade|país)\)", "", t)  # "(Brasil)" do nome do artigo
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"\s+([,.!?])", r"\1", t).strip()


# Quando nada do que está em alta serve, o canal usa estes temas que mais despertam curiosidade
# (um por vez, em rodízio diário, para variar).
CATEGORIAS_CURIOSAS = [
    "lugares mal-assombrados reais e famosos (no Brasil ou no mundo) e a história documentada por trás das lendas",
    "desaparecimentos e casos reais que nunca foram resolvidos",
    "cidades, hospitais, hotéis ou parques abandonados e o que aconteceu ali",
    "objetos amaldiçoados ou enigmáticos guardados em museus",
    "sons, sinais e fenômenos estranhos registrados por cientistas e ainda sem explicação completa",
    "descobertas arqueológicas que mudaram o que se sabia da história",
    "lugares proibidos ou inacessíveis ao público e por quê",
    "lendas e criaturas famosas que nasceram de fatos reais",
    "mistérios do fundo do mar e das profundezas",
    "OVNIs e casos investigados oficialmente por governos ou forças armadas",
    "construções antigas que até hoje intrigam engenheiros e historiadores",
    "acontecimentos bizarros e reais da história do Brasil",
]


def tema_curioso(formato: str = "curto") -> str:
    from datetime import date
    i = (date.today().toordinal() * 2 + (formato == "longo")) % len(CATEGORIAS_CURIOSAS)
    return (f"Escolha UM caso real, específico e documentado desta categoria: {CATEGORIAS_CURIOSAS[i]}. "
            "Prefira o que gera MUITA curiosidade (a pessoa precisa querer ver o final), com nome, lugar e data, "
            "e que tenha fotos reais do lugar ou do objeto.")


def gerar(tema: str | None, usados: list[str]) -> dict:
    """Retorna dict com assunto, titulo, roteiro, descricao, hashtags e cenas."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        print("⚠️  Sem GROQ_API_KEY nem GEMINI_API_KEY: usando roteiro de exemplo.")
        return dict(EXEMPLO)

    segundos = config.DURACAO_ALVO_SEGUNDOS
    prompt = PROMPT.format(
        nicho=config.NICHO,
        tema_linha=f"Tema obrigatório deste vídeo: {tema}" if tema else tema_curioso("curto"),
        usados=", ".join(usados[-60:]) or "nenhum",
        idioma=config.IDIOMA,
        segundos=segundos,
        palavras=int(segundos * 2.1),  # a voz neural + pausas fala ~2,1 palavras/s
        cenas=max(6, round(segundos / 7)),
    )
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    minimo = int(segundos * 2.1 * 0.85)
    dados = pedir(prompt)
    for _ in range(2):  # a IA às vezes escreve curto demais: pede para expandir
        qtd = len(str(dados.get("roteiro", "")).split())
        if qtd >= minimo:
            break
        print(f"   roteiro com {qtd} palavras (mínimo {minimo}), pedindo versão maior...")
        dados = pedir(prompt + f"\n\nATENÇÃO: sua versão anterior tinha só {qtd} palavras. "
                               f"Escreva de novo com NO MÍNIMO {int(segundos * 2.6)} palavras.")

    faltando = {"titulo", "roteiro", "cenas"} - dados.keys()
    if faltando:
        raise ValueError(f"Roteiro veio incompleto, faltou: {faltando}")
    dados["roteiro"] = limpar_narracao(dados["roteiro"])
    dados.setdefault("assunto", dados["titulo"])
    dados.setdefault("descricao", "")
    dados.setdefault("hashtags", ["#shorts"])
    dados["titulo"] = dados["titulo"][:95]
    return dados


# ───────────────────────── VÍDEO LONGO (YouTube 16:9) ─────────────────────────
PROMPT_LONGO = """Você é roteirista de um canal do YouTube de vídeos longos e envolventes.

Nicho do canal: {nicho}
{tema_linha}
Assuntos que JÁ foram usados (não repita): {usados}

Escreva o roteiro de UM vídeo em {idioma} de cerca de {minutos} minutos de narração
(no total, NO MÍNIMO {palavras} palavras), no formato de lista/top ou de história em capítulos.

Estrutura obrigatória:
- Parte 1 = introdução: gancho forte nos primeiros 10 segundos, diga o que a pessoa vai descobrir e peça para se inscrever no canal.
- Partes do meio: {partes_meio} partes, cada uma com um subtítulo e de {por_parte} palavras,
  com fatos verdadeiros, exemplos e curiosidades (números só se tiver certeza absoluta; em notícia, só os do pedido). Faça transições que prendam ("mas o mais estranho ainda está por vir").
- Última parte = conclusão curta + pergunta para comentarem + convite para se inscrever.

Regras: linguagem falada, frases curtas, sem emojis, sem indicações de cena, só fatos verdadeiros e verificáveis.
Eleição, política, saúde e notícias: nunca apresente previsão como resultado certo nem invente números.
Mistérios: só casos reais e documentados; separe o que é fato comprovado do que é teoria ou lenda.

Responda SOMENTE com um JSON neste formato:
{{
  "assunto": "assunto em poucas palavras",
  "titulo": "título chamativo para YouTube com até 70 caracteres",
  "descricao": "descrição de 3 a 5 frases para o YouTube, com palavras-chave",
  "hashtags": ["#curiosidades", "#outra", "#outra"],
  "partes": [
    {{"titulo": "Introdução", "texto": "narração completa desta parte", "cenas": ["4 a 6 cenas desta parte: termo de busca EM INGLÊS com o objeto/lugar LITERAL (ex: 'deep ocean'); 'wiki:Nome completo do artigo' para pessoa/lugar/objeto real famoso (ex: 'wiki:Pelé', 'wiki:Luiz Inácio Lula da Silva', nunca apelido como 'wiki:Lula'); 'ia:descrição em inglês' para coisas imaginadas (ET, nave, criatura, assombração) — em vídeos de ETs/OVNIs, pelo menos metade das cenas 'ia:'; em lugares mal-assombrados, o lugar real como 'wiki:' e o clima da lenda como 'ia:'. Evite escritório, reuniões e finanças"]}}
  ]
}}"""


def _contar(dados: dict) -> int:
    return sum(len(str(p.get("texto", "")).split()) for p in dados.get("partes", []))


def gerar_longo(tema: str | None, usados: list[str]) -> dict:
    """Roteiro em partes para o vídeo longo. Retorna também 'roteiro' (texto inteiro)."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        raise RuntimeError("O vídeo longo precisa da IA do roteiro (GROQ_API_KEY).")
    minutos = config.DURACAO_LONGO_MINUTOS
    palavras = int(minutos * 60 * 2.5)
    partes_meio = max(4, min(10, minutos))
    prompt = PROMPT_LONGO.format(
        nicho=config.NICHO,
        tema_linha=f"Tema obrigatório deste vídeo: {tema}" if tema else tema_curioso("longo"),
        usados=", ".join(usados[-60:]) or "nenhum",
        idioma=config.IDIOMA,
        minutos=minutos,
        palavras=palavras,
        partes_meio=partes_meio,
        por_parte=int(palavras * 0.85 / partes_meio),
    )
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    dados = pedir(prompt)
    for _ in range(2):
        qtd = _contar(dados)
        if qtd >= palavras * 0.8 and len(dados.get("partes", [])) >= 4:
            break
        print(f"   roteiro longo com {qtd} palavras (meta {palavras}), pedindo versão maior...")
        dados = pedir(prompt + f"\n\nATENÇÃO: a versão anterior tinha só {qtd} palavras no total. "
                               f"Escreva de novo com NO MÍNIMO {palavras} palavras, desenvolvendo bem cada parte.")

    partes = [p for p in dados.get("partes", []) if str(p.get("texto", "")).strip()]
    if len(partes) < 3:
        raise ValueError("Roteiro longo veio sem partes suficientes.")
    for p in partes:
        p["texto"] = limpar_narracao(p["texto"])
        p["titulo"] = str(p.get("titulo") or "Parte").strip()[:60]
        p["cenas"] = [c for c in p.get("cenas", []) if str(c).strip()][:6] or [dados.get("assunto", "nature")]
    dados["partes"] = partes
    dados["roteiro"] = "\n\n".join(p["texto"] for p in partes)
    dados["cenas"] = [c for p in partes for c in p["cenas"]]
    dados.setdefault("assunto", dados.get("titulo", "vídeo longo"))
    dados.setdefault("descricao", "")
    dados.setdefault("hashtags", ["#curiosidades"])
    dados["titulo"] = str(dados.get("titulo", dados["assunto"]))[:95]
    print(f"   roteiro longo: {len(partes)} partes, {_contar(dados)} palavras")
    return dados


# ───────────────────────── TÍTULO E DESCRIÇÃO VIRALIZANTES ─────────────────────────
PROMPT_VIRAL = """Você é especialista em crescimento de canais no TikTok e no YouTube, focado em {idioma}.
Crie os textos de publicação deste vídeo para MAXIMIZAR cliques, retenção e alcance.

Formato do vídeo: {formato_desc}
Nicho: {nicho}
Assunto: {assunto}
Roteiro (resumo): {resumo}

Técnicas obrigatórias:
- Título com "lacuna de curiosidade": desperta a pergunta sem entregar a resposta.
  Use número, contraste, segredo, exagero plausível ou "ninguém te conta". Palavra-chave do assunto no começo.
- Nada de mentira ou promessa que o vídeo não cumpre (isso derruba a retenção e o alcance).
- VARIE as fórmulas: NÃO use a palavra "segredo"/"segredos" (o canal já usou demais) nem "ninguém te conta".
- Notícia, eleição, política, economia ou saúde: título e capa INFORMATIVOS e neutros (ex.: "os 8 desafios do
  próximo governo"), sem sensacionalismo, sem "o que não querem que você veja".
- Português impecável: revise concordância e grafia (ex.: "sinais misteriosos", nunca "sinais mistérios").
- Eleição/política: nada de "resultado cravado" ou "vai ganhar com certeza"; use "análise", "o que as pesquisas mostram".
- Escreva como gente fala, sem soar como propaganda.

Responda SOMENTE com um JSON:
{{
  "titulo_youtube": "até 60 caracteres, com 1 palavra em MAIÚSCULAS para destacar, palavra-chave no início",
  "descricao_youtube": "descrição envolvente em 4 blocos separados por linha em branco (use \\n\\n): 1) gancho de 1-2 frases que conta o essencial do caso com a palavra-chave e 1 emoji; 2) contexto com 1-3 fatos concretos e verdadeiros QUE ESTÃO NO ROTEIRO (nomes, lugares, anos); 3) uma pergunta provocativa para comentarem + 1 emoji; 4) convite para se inscrever{canal_txt}. Tom de conversa, sem exagero, sem lista de minutos/capítulos, sem hashtags (elas vão à parte), no máximo 900 caracteres",
  "legenda_tiktok": "1ª linha = gancho curto que provoca (até 80 caracteres, pode ter 1 emoji); 2ª linha = pergunta que incentive comentários; sem hashtags aqui",
  "hashtags_tiktok": ["5 a 7 hashtags: 2 amplas (ex: #curiosidades #fyp), 3 do assunto específico, 1 do nicho em português"],
  "hashtags_youtube": ["3 a 5 hashtags relevantes"],
  "texto_capa": "frase da thumbnail: 2 a 4 palavras de impacto em português, ligadas ao tema concreto do vídeo (ex: 'A ILHA PROIBIDA', '8 DESAFIOS DO BRASIL'); nunca 'segredo'",
  "prompt_capa": "descrição EM INGLÊS de UMA cena cinematográfica e chamativa para a thumbnail deste vídeo (o objeto/lugar principal do tema, em close, iluminação dramática), sem texto",
  "titulo_short": "título de um Short de 1 minuto que divulga este vídeo (até 55 caracteres, provoca curiosidade, palavra-chave no início)",
  "tags_youtube": ["10 a 15 palavras-chave de busca em português, do específico ao amplo"]
}}"""


REGRAS_NOTICIA = """
ATENÇÃO, ESTE VÍDEO É NOTÍCIA SOBRE PESSOAS REAIS. Estas regras valem MAIS que as técnicas acima:
- Título, capa, título do Short e legendas INFORMATIVOS e neutros, em forma de pergunta ou "o que se sabe"
  (ex.: "X deixou o país? O que se sabe até agora"). Sem MAIÚSCULAS de impacto, sem "fuga", "escândalo",
  "desaparecido", "verdade", "ninguém previu", "chocante".
- Nunca afirme como fato o que é alegação; use "teria", "suposta", "segundo".
- Só use fatos, números, datas e porcentagens que estão em FATOS E REGRAS DO PEDIDO.
- A pergunta para comentarem não pode sugerir culpa nem teoria da conspiração.
FATOS E REGRAS DO PEDIDO:
{tema}
"""


def modo_noticia(tema: str | None) -> bool:
    """Pedido de notícia (pessoas reais, fatos do dia): títulos neutros e checagem de fatos."""
    return bool(tema) and bool(re.search(r"not[íi]cia|jornal[íi]stic", tema, re.I))


PROMPT_REVISAO = """Você é checador de fatos de um canal de notícias em {idioma}.

FATOS E REGRAS DO PEDIDO (a única fonte sobre o caso):
{tema}

Abaixo estão os textos de um vídeo em JSON. Corrija SOMENTE o que violar as regras:
1) afirmações sobre o caso que não estão nos FATOS (corte ou troque pelo fato correto);
2) números, datas e porcentagens que não estão nos FATOS (corte; explicações gerais sem números podem ficar);
3) alegações apresentadas como certeza ou acusação (troque por "teria", "suposta", "segundo");
4) títulos, capa e legendas sensacionalistas (deixe informativos e neutros, sem MAIÚSCULAS de impacto).
Explicações gerais sobre leis e instituições podem ficar, se estiverem corretas e sem números inventados.
A narração ("partes") é o texto FALADO: nunca escreva nela 'wiki:', 'ia:' nem listas de cenas.
Mantenha o resto do texto igual e com tamanho parecido (a narração já tem duração certa).

TEXTOS:
{textos}

Responda SOMENTE com o mesmo JSON corrigido (mesmas chaves e o mesmo número de itens em "partes")."""


# em notícia sobre pessoa real, estes termos acusam (ou inventam crime) e não podem ir ao ar
PROIBIDAS_NOTICIA = ("identidade falsa", "documento falso", "documentos falsos", "passaporte falso", "fugiu", "fuga de",
                     "foragido", "fugitivo", "criminoso", "culpado", "desaparecido", "escondido", "escondendo")


def _proibidas(dados: dict) -> list[str]:
    texto = " ".join(str(dados.get(k, "")) for k in ("roteiro", "titulo", "descricao", "texto_capa", "titulo_short",
                                                     "legenda_tiktok")).lower()
    return [p for p in PROIBIDAS_NOTICIA if p in texto]


def revisar_noticia(dados: dict, tema: str, _tentativa: int = 1) -> dict:
    """Checagem de fatos dos vídeos de notícia antes de gravar a narração.
    Se sobrar termo acusatório depois de 2 revisões, o vídeo NÃO é publicado."""
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    longo = bool(dados.get("partes"))
    chaves = ["titulo", "descricao", "texto_capa", "titulo_short", "legenda_tiktok"]
    textos = {k: dados.get(k, "") for k in chaves}
    textos["partes"] = [p["texto"] for p in dados["partes"]] if longo else [dados.get("roteiro", "")]
    try:
        r = pedir(PROMPT_REVISAO.format(idioma=config.IDIOMA, tema=tema, textos=json.dumps(textos, ensure_ascii=False)))
    except Exception as erro:
        print(f"   ⚠️  checagem de fatos falhou ({erro}); mantendo os textos.")
        return dados
    partes = [str(x).strip() for x in r.get("partes", [])]
    if len(partes) == len(textos["partes"]) and all(len(p.split()) >= 0.7 * len(o.split()) for p, o in zip(partes, textos["partes"])):
        partes = [limpar_narracao(p) for p in partes]
        if longo:
            for p, novo in zip(dados["partes"], partes):
                p["texto"] = novo
            dados["roteiro"] = "\n\n".join(partes)
        else:
            dados["roteiro"] = partes[0]
    else:
        print("   ⚠️  checagem de fatos devolveu a narração cortada demais; mantendo a narração original.")
    for k in chaves:
        if str(r.get(k, "")).strip():
            dados[k] = str(r[k]).strip()
    dados["titulo"] = dados["titulo"][:95]
    # trava final: porcentagem que não está no pedido sai da descrição e das legendas
    ok = set(re.findall(r"\d+(?:[.,]\d+)?\s?%", tema))
    for k in ("descricao", "legenda_tiktok"):
        frases = re.split(r"(?<=[.!?])\s+", str(dados.get(k, "")))
        dados[k] = " ".join(f for f in frases if all(n in ok for n in re.findall(r"\d+(?:[.,]\d+)?\s?%", f)))
    soltos = [n for n in re.findall(r"\d+(?:[.,]\d+)?\s?%", dados.get("roteiro", "")) if n not in ok]
    if soltos:
        print(f"::warning title=Checagem::a narração cita números que não estão no pedido: {soltos}")
    if re.search(r"\bwiki\b|\bia\s*:", dados.get("roteiro", ""), re.I):
        raise RuntimeError("Vídeo NÃO publicado: a narração ainda tem marcas de cena (wiki:/ia:).")
    achados = _proibidas(dados)
    if achados:
        if _tentativa >= 2:
            raise RuntimeError(f"Vídeo de notícia NÃO publicado: o texto ainda acusa ou inventa ({achados}).")
        print(f"   ⚠️  termos proibidos na notícia: {achados}; revisando de novo")
        tema_mais = (f"{tema}\nPROIBIDO usar estes termos (são falsos ou acusatórios): {', '.join(achados)}. "
                     "Não invente documento falso, crime nem fuga que os FATOS não citam.")
        return revisar_noticia(dados, tema_mais, _tentativa + 1)
    print(f"   🔎 checagem de fatos feita → {dados['titulo']}")
    return dados


def textos_virais(dados: dict, formato: str = "curto", tema: str | None = None) -> dict:
    """Gera título, descrição e hashtags otimizados para cada rede e junta em `dados`."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        return dados
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    prompt = PROMPT_VIRAL.format(
        canal_txt=f" no canal {config.CANAL}" if config.CANAL else "",
        idioma=config.IDIOMA,
        formato_desc="vídeo curto vertical (TikTok / YouTube Shorts)" if formato == "curto"
        else "vídeo longo horizontal para YouTube, com capítulos",
        nicho=config.NICHO,
        assunto=dados.get("assunto", ""),
        resumo=str(dados.get("roteiro", ""))[:1800],
    )
    if modo_noticia(tema):
        prompt += REGRAS_NOTICIA.format(tema=tema)
    try:
        v = pedir(prompt)
    except Exception as erro:
        print(f"   ⚠️  não consegui gerar os textos virais ({erro}); usando os do roteiro.")
        return dados

    def lista(chave, limite):
        itens = [str(h).strip() for h in v.get(chave, []) if str(h).strip()]
        return [h if h.startswith("#") or chave.startswith("tags") else "#" + h.replace(" ", "") for h in itens][:limite]

    if v.get("titulo_youtube"):
        dados["titulo"] = str(v["titulo_youtube"]).strip()[:95]
    if v.get("descricao_youtube"):
        dados["descricao"] = str(v["descricao_youtube"]).strip()
    dados["legenda_tiktok"] = str(v.get("legenda_tiktok") or dados.get("titulo", "")).strip()
    dados["hashtags_tiktok"] = lista("hashtags_tiktok", 7) or dados.get("hashtags", [])
    dados["hashtags"] = lista("hashtags_youtube", 5) or dados.get("hashtags", [])
    dados["tags_youtube"] = lista("tags_youtube", 15)
    dados["texto_capa"] = str(v.get("texto_capa") or "").strip()[:40]
    dados["prompt_capa"] = str(v.get("prompt_capa") or "").strip()[:400]
    dados["titulo_short"] = str(v.get("titulo_short") or dados.get("titulo", "")).strip()[:90]
    print(f"   ✨ título viral: {dados['titulo']}")
    return dados
