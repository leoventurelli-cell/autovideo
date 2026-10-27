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

def falhar(msg: str):
    """Mostra o erro em destaque no resumo da execução do GitHub (Annotations)."""
    print(f"::error title=Conexão com o TikTok::{msg}")
    raise SystemExit(msg)


if not config.TIKTOK_CLIENT_KEY:
    falhar("Falta o Client key do TikTok (variável TIKTOK_CLIENT_KEY).")
if not config.TIKTOK_CLIENT_SECRET:
    falhar("Falta o segredo TIKTOK_CLIENT_SECRET no GitHub.")

colado = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not colado:
    falhar("Cole o código (ou o endereço completo) que apareceu no painel depois de autorizar.")

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
try:
    dados = r.json()
except ValueError:
    falhar(f"Resposta inesperada do TikTok ({r.status_code}): {r.text[:200]}")
if "refresh_token" not in dados:
    erro = dados.get("error", "?")
    detalhe = dados.get("error_description", "")
    dica = {
        "invalid_client": "o Client secret não confere com o Client key. Confira se colou o secret do SANDBOX.",
        "invalid_grant": "o código venceu ou já foi usado. Clique de novo em 'Conectar TikTok' e conclua em seguida.",
        "invalid_request": "o endereço de retorno (Redirect URI) não confere com o cadastrado no app.",
    }.get(erro, "veja o detalhe acima.")
    falhar(f"TikTok recusou ({erro}): {detalhe} → Provável causa: {dica} "
           f"[client_key={config.TIKTOK_CLIENT_KEY}, redirect={config.TIKTOK_REDIRECT_URI}]")

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
try:
    import publicar_tiktok
    conta = publicar_tiktok.info_do_criador()
    print(f"   Conta: {conta.get('apelido') or conta}")
except Exception as erro:
    print(f"   (não consegui ler a conta: {erro})")
if "video.publish" not in escopos:
    print("   ⚠️  Faltou a permissão video.publish: ative 'Direct Post' na Content Posting API do seu app.")
