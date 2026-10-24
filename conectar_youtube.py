"""
Troca o código de autorização do Google pelo acesso ao canal e guarda criptografado.
Roda pelo GitHub (Actions → "Conectar YouTube"), sem instalar nada.
"""
import json
import sys
import urllib.parse

import requests

import config
import youtube_token


def falhar(msg: str):
    print(f"::error title=Conexão com o YouTube::{msg}")
    raise SystemExit(msg)


if not config.YT_CLIENT_ID:
    falhar("Falta o ID do cliente do Google (variável YT_CLIENT_ID).")
if not config.YT_CLIENT_SECRET:
    falhar("Falta o segredo YT_CLIENT_SECRET no GitHub.")

colado = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not colado:
    falhar("Cole o código que apareceu no painel depois de autorizar o YouTube.")
params = urllib.parse.parse_qs(urllib.parse.urlparse(colado).query)
codigo = params.get("code", [colado])[0]

r = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": codigo,
        "client_id": config.YT_CLIENT_ID,
        "client_secret": config.YT_CLIENT_SECRET,
        "redirect_uri": config.TIKTOK_REDIRECT_URI,  # o mesmo endereço do painel
        "grant_type": "authorization_code",
    },
    timeout=30,
)
dados = r.json()
if "refresh_token" not in dados:
    erro = dados.get("error", "?")
    dica = {
        "invalid_grant": "o código venceu ou já foi usado. Clique de novo em 'Conectar YouTube' e conclua em seguida.",
        "invalid_client": "o YT_CLIENT_SECRET não confere com o ID do cliente.",
        "redirect_uri_mismatch": "cadastre no Google o URI de redirecionamento do painel.",
    }.get(erro, "veja o detalhe.")
    if "access_token" in dados:
        dica = "o Google não enviou o refresh token. Remova o acesso em myaccount.google.com/permissions e conecte de novo."
    falhar(f"Google recusou ({erro}): {dados.get('error_description', '')} → {dica} [redirect={config.TIKTOK_REDIRECT_URI}]")

youtube_token.salvar(dados["refresh_token"])

# descobre o nome do canal para mostrar no painel
canal = ""
try:
    c = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                     headers={"Authorization": f"Bearer {dados['access_token']}"}, timeout=30).json()
    canal = c["items"][0]["snippet"]["title"]
except Exception:
    pass

painel = config.PASTA / "docs" / "config.json"
cfg = json.loads(painel.read_text(encoding="utf-8")) if painel.exists() else {}
cfg.update({"youtube_conectado": True, "youtube_client_id": config.YT_CLIENT_ID, "youtube_canal": canal})
painel.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"::notice title=YouTube conectado::Canal: {canal or '(não consegui ler o nome)'}")
print("✅ YouTube conectado!")
