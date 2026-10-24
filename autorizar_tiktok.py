"""
Rode UMA VEZ para autorizar o envio à sua conta do TikTok:

    python autorizar_tiktok.py

Antes, preencha no .env: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET e
TIKTOK_REDIRECT_URI (a mesma URL cadastrada no app do TikTok for Developers).
"""
import secrets
import urllib.parse

import requests

import config

if not (config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET and config.TIKTOK_REDIRECT_URI):
    raise SystemExit("Preencha TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET e TIKTOK_REDIRECT_URI no .env primeiro.")

estado = secrets.token_urlsafe(16)
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": config.TIKTOK_CLIENT_KEY,
    "scope": "user.info.basic,video.upload,video.publish",
    "response_type": "code",
    "redirect_uri": config.TIKTOK_REDIRECT_URI,
    "state": estado,
})
print("1) Abra este link no navegador e autorize:\n")
print(url)
print("\n2) Você vai cair na sua URL de retorno (pode até dar erro 404, tudo bem).")
print("   Copie o endereço COMPLETO da barra do navegador e cole aqui.\n")

colado = input("Endereço: ").strip()
params = urllib.parse.parse_qs(urllib.parse.urlparse(colado).query)
codigo = params.get("code", [colado])[0]

r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "client_key": config.TIKTOK_CLIENT_KEY,
        "client_secret": config.TIKTOK_CLIENT_SECRET,
        "code": codigo,
        "grant_type": "authorization_code",
        "redirect_uri": config.TIKTOK_REDIRECT_URI,
    },
    timeout=30,
)
dados = r.json()
if "refresh_token" not in dados:
    raise SystemExit(f"Não deu certo: {dados}")

print("\n✅ Autorizado! Coloque isto no seu .env (e nos Secrets do GitHub):\n")
print(f"TIKTOK_REFRESH_TOKEN={dados['refresh_token']}")
print(f"\n(o refresh token vale por {int(dados.get('refresh_expires_in', 0)) // 86400} dias)")
