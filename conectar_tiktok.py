"""
Troca o código de autorização do TikTok pelo token de acesso e guarda criptografado.
Roda pelo GitHub (Actions → "Conectar TikTok"), sem instalar nada.

    python conectar_tiktok.py "<código ou endereço completo da página de retorno>"
"""
import sys
import urllib.parse

import requests

import config
import tiktok_token

colado = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not colado:
    raise SystemExit("Cole o código (ou o endereço completo) que apareceu no painel depois de autorizar.")

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
    erro = dados.get("error_description") or dados.get("error") or dados
    raise SystemExit(
        f"O TikTok não aceitou o código: {erro}\n"
        "O código vale poucos minutos e só pode ser usado uma vez. "
        "Clique de novo em 'Conectar TikTok' no painel e rode este passo logo em seguida."
    )

tiktok_token.salvar(dados["refresh_token"])

import json
painel = config.PASTA / "docs" / "config.json"
cfg = json.loads(painel.read_text(encoding="utf-8")) if painel.exists() else {}
cfg["tiktok_conectado"] = True
cfg["tiktok_client_key"] = config.TIKTOK_CLIENT_KEY
painel.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
escopos = dados.get("scope", "")
print("✅ TikTok conectado!")
print(f"   Permissões: {escopos}")
print(f"   A conexão vale {int(dados.get('refresh_expires_in', 0)) // 86400} dias e se renova a cada vídeo publicado.")
if "video.publish" not in escopos:
    print("   ⚠️  Faltou a permissão video.publish: ative 'Direct Post' na Content Posting API do seu app.")
