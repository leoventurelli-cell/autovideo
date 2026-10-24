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
  "cenas": ["{cenas} termos de busca EM INGLÊS para vídeos de banco, um por cena, na ordem da narração, ex: 'deep ocean', 'ancient pyramid'"]
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


def _pedir_ao_groq(prompt: str) -> dict:
    """Groq: plano gratuito em https://console.groq.com/keys (chave começa com gsk_)."""
    candidatos = [config.GROQ_MODELO] if config.GROQ_MODELO else []
    lista_carregada = False
    esperas = 0
    while True:
        if not candidatos:
            if lista_carregada:
                raise RuntimeError("Nenhum modelo do Groq aceitou o pedido.")
            candidatos, lista_carregada = _modelos_groq()[:5], True
        modelo = candidatos[0]
        r = requests.post(
            f"{GROQ_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            json={
                "model": modelo,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 1.0,
                "response_format": {"type": "json_object"},
            },
            timeout=120,
        )
        if r.status_code == 429 and esperas < 4:  # limite do plano grátis
            esperas += 1
            time.sleep(20)
            continue
        if r.status_code in (400, 404) and "model" in r.text.lower():
            # modelo aposentado ou sem suporte a JSON: tenta o próximo
            print(f"   modelo {modelo} indisponível, tentando outro...")
            candidatos = candidatos[1:]
            continue
        if r.status_code in (401, 403):
            raise RuntimeError("Groq recusou a chave. Confira o segredo GROQ_API_KEY (começa com 'gsk_').")
        r.raise_for_status()
        print(f"   (roteiro escrito pelo modelo {modelo} no Groq)")
        return json.loads(r.json()["choices"][0]["message"]["content"])


def gerar(tema: str | None, usados: list[str]) -> dict:
    """Retorna dict com assunto, titulo, roteiro, descricao, hashtags e cenas."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        print("⚠️  Sem GROQ_API_KEY nem GEMINI_API_KEY: usando roteiro de exemplo.")
        return dict(EXEMPLO)

    segundos = config.DURACAO_ALVO_SEGUNDOS
    prompt = PROMPT.format(
        nicho=config.NICHO,
        tema_linha=f"Tema obrigatório deste vídeo: {tema}" if tema else "Escolha você um assunto que viralize.",
        usados=", ".join(usados[-60:]) or "nenhum",
        idioma=config.IDIOMA,
        segundos=segundos,
        palavras=int(segundos * 2.6),
        cenas=max(6, round(segundos / 7)),
    )
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    minimo = int(segundos * 2.6 * 0.85)
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
  com fatos verdadeiros, exemplos, números e curiosidades. Faça transições que prendam ("mas o mais estranho ainda está por vir").
- Última parte = conclusão curta + pergunta para comentarem + convite para se inscrever.

Regras: linguagem falada, frases curtas, sem emojis, sem indicações de cena, só fatos verdadeiros e verificáveis.

Responda SOMENTE com um JSON neste formato:
{{
  "assunto": "assunto em poucas palavras",
  "titulo": "título chamativo para YouTube com até 70 caracteres",
  "descricao": "descrição de 3 a 5 frases para o YouTube, com palavras-chave",
  "hashtags": ["#curiosidades", "#outra", "#outra"],
  "partes": [
    {{"titulo": "Introdução", "texto": "narração completa desta parte", "cenas": ["4 a 6 termos de busca EM INGLÊS para vídeos de banco, ex: 'deep ocean'"]}}
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
        tema_linha=f"Tema obrigatório deste vídeo: {tema}" if tema else "Escolha você um assunto com muito potencial de busca no YouTube.",
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
- Escreva como gente fala, sem soar como propaganda.

Responda SOMENTE com um JSON:
{{
  "titulo_youtube": "até 60 caracteres, com 1 palavra em MAIÚSCULAS para destacar, palavra-chave no início",
  "descricao_youtube": "3 a 5 frases: a 1ª repete a promessa do título com a palavra-chave; depois resume o que a pessoa vai aprender; termina pedindo inscrição e comentário com uma pergunta",
  "legenda_tiktok": "1ª linha = gancho curto que provoca (até 80 caracteres, pode ter 1 emoji); 2ª linha = pergunta que incentive comentários; sem hashtags aqui",
  "hashtags_tiktok": ["5 a 7 hashtags: 2 amplas (ex: #curiosidades #fyp), 3 do assunto específico, 1 do nicho em português"],
  "hashtags_youtube": ["3 a 5 hashtags relevantes"],
  "tags_youtube": ["10 a 15 palavras-chave de busca em português, do específico ao amplo"]
}}"""


def textos_virais(dados: dict, formato: str = "curto") -> dict:
    """Gera título, descrição e hashtags otimizados para cada rede e junta em `dados`."""
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        return dados
    pedir = _pedir_ao_groq if config.GROQ_API_KEY else _pedir_ao_gemini
    prompt = PROMPT_VIRAL.format(
        idioma=config.IDIOMA,
        formato_desc="vídeo curto vertical (TikTok / YouTube Shorts)" if formato == "curto"
        else "vídeo longo horizontal para YouTube, com capítulos",
        nicho=config.NICHO,
        assunto=dados.get("assunto", ""),
        resumo=str(dados.get("roteiro", ""))[:1800],
    )
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
    print(f"   ✨ título viral: {dados['titulo']}")
    return dados
