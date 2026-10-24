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

Responda SOMENTE com um JSON neste formato:
{{
  "assunto": "assunto em poucas palavras",
  "titulo": "título chamativo com até 70 caracteres",
  "roteiro": "texto completo da narração",
  "descricao": "descrição de 2 ou 3 frases para o post",
  "hashtags": ["#exemplo", "#outra", "#shorts"],
  "cenas": ["5 a 7 termos de busca EM INGLÊS para vídeos de banco, um por cena, na ordem da narração, ex: 'deep ocean', 'ancient pyramid'"]
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
    )
    dados = _pedir_ao_groq(prompt) if config.GROQ_API_KEY else _pedir_ao_gemini(prompt)

    faltando = {"titulo", "roteiro", "cenas"} - dados.keys()
    if faltando:
        raise ValueError(f"Roteiro veio incompleto, faltou: {faltando}")
    dados.setdefault("assunto", dados["titulo"])
    dados.setdefault("descricao", "")
    dados.setdefault("hashtags", ["#shorts"])
    dados["titulo"] = dados["titulo"][:95]
    return dados
