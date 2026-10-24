"""
Configurações do AutoVídeo.
Tudo que é segredo (chaves e tokens) vem de variáveis de ambiente
ou de um arquivo .env na pasta do projeto. Nunca coloque chaves aqui.
"""
import os
from pathlib import Path

PASTA = Path(__file__).parent


def _carregar_env():
    """Lê o arquivo .env (formato CHAVE=valor) se ele existir."""
    arquivo = PASTA / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()


def _env(nome: str, padrao: str = "") -> str:
    """Como os.getenv, mas trata variável vazia como não definida."""
    return os.getenv(nome) or padrao

# ───────────────────────── CONTEÚDO ─────────────────────────
# Troque o nicho aqui. Exemplos: "curiosidades sobre o espaço",
# "histórias de terror curtas", "fatos sobre animais", "dicas de dinheiro"
NICHO = _env("NICHO", "curiosidades incríveis e pouco conhecidas sobre o mundo")
IDIOMA = "português do Brasil"
DURACAO_ALVO_SEGUNDOS = int(_env("DURACAO_ALVO", "75"))  # TikTok paga só vídeos com mais de 1 minuto

# ───────────────────────── IA DO ROTEIRO ─────────────────────────
# Groq (grátis): https://console.groq.com/keys — se houver chave, ele é usado.
GROQ_API_KEY = _env("GROQ_API_KEY", "")
GROQ_MODELO = _env("GROQ_MODELO", "openai/gpt-oss-120b")  # se sair do ar, escolhe outro sozinho
# Gemini (alternativa grátis): https://aistudio.google.com/apikey
GEMINI_API_KEY = _env("GEMINI_API_KEY", "")
GEMINI_MODELO = _env("GEMINI_MODELO", "gemini-2.5-flash")

# ───────────────────────── VOZ ─────────────────────────
# Vozes em português: pt-BR-FranciscaNeural, pt-BR-AntonioNeural, pt-BR-ThalitaNeural
VOZ = _env("VOZ", "pt-BR-AntonioNeural")
VELOCIDADE_VOZ = _env("VELOCIDADE_VOZ", "+8%")  # um pouco mais rápido prende mais

# ───────────────────────── VÍDEO ─────────────────────────
# Banco de vídeos grátis: https://www.pexels.com/api/
PEXELS_API_KEY = _env("PEXELS_API_KEY", "")
LARGURA, ALTURA, FPS = 1080, 1920, 30
FONTE_LEGENDA = "Poppins"           # arquivo em fontes/
COR_DESTAQUE = "&H0000E5FF"         # amarelo (formato ASS: &HAABBGGRR)
VOLUME_MUSICA = float(_env("VOLUME_MUSICA", "0.12"))  # se houver mp3 em musica/

# ───────────────────────── PUBLICAÇÃO ─────────────────────────
PUBLICAR_YOUTUBE = _env("PUBLICAR_YOUTUBE", "sim") == "sim"
PUBLICAR_TIKTOK = _env("PUBLICAR_TIKTOK", "sim") == "sim"

# YouTube: "public", "unlisted" ou "private".
# Enquanto seu projeto do Google não passar na auditoria da API,
# o YouTube força "private" de qualquer jeito.
YT_PRIVACIDADE = _env("YT_PRIVACIDADE", "public")
YT_CLIENT_ID = _env("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = _env("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = _env("YT_REFRESH_TOKEN", "")
YT_CATEGORIA = _env("YT_CATEGORIA", "27")  # 27 = Educação, 24 = Entretenimento

# TikTok:
#   "direto"   → publica sozinho com título e descrição da IA. Enquanto o TikTok não
#                aprovar seu app, ele cai automaticamente no modo rascunho.
#   "rascunho" → manda o vídeo para a caixa de entrada do app; você só toca em Publicar.
TIKTOK_MODO = _env("TIKTOK_MODO", "direto")
TIKTOK_CLIENT_KEY = _env("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = _env("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REFRESH_TOKEN = _env("TIKTOK_REFRESH_TOKEN", "")


def _site_padrao() -> str:
    """Endereço do painel no GitHub Pages: https://usuario.github.io/repositorio/"""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repo:
        dono, nome = repo.split("/", 1)
        return f"https://{dono.lower()}.github.io/{nome}/"
    return ""


TIKTOK_REDIRECT_URI = _env("TIKTOK_REDIRECT_URI", _site_padrao())
# Se a opção não estiver liberada para a conta, usa a primeira que o TikTok permitir.
TIKTOK_PRIVACIDADE = _env("TIKTOK_PRIVACIDADE", "PUBLIC_TO_EVERYONE")
# Marca o post como conteúdo gerado por IA (recomendado pelas regras do TikTok)
TIKTOK_ROTULO_IA = True

# ───────────────────────── ARQUIVOS ─────────────────────────
PASTA_SAIDA = PASTA / "saida"
PASTA_FONTES = PASTA / "fontes"
PASTA_MUSICA = PASTA / "musica"
ARQUIVO_TEMAS = PASTA / "temas.txt"         # opcional: um tema por linha
ARQUIVO_HISTORICO = PASTA / "historico.json"  # evita repetir assuntos
