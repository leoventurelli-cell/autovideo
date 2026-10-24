"""
Rode UMA VEZ no seu computador para autorizar o envio ao seu canal:

    python autorizar_youtube.py

Precisa do arquivo client_secret.json baixado do Google Cloud
(passo a passo no LEIAME.md). No fim, ele mostra o YT_REFRESH_TOKEN.
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]
arquivo = Path(__file__).parent / "client_secret.json"
if not arquivo.exists():
    raise SystemExit("Coloque o client_secret.json (OAuth tipo 'App para computador') nesta pasta.")

fluxo = InstalledAppFlow.from_client_secrets_file(str(arquivo), ESCOPOS)
cred = fluxo.run_local_server(port=0, prompt="consent", access_type="offline")

segredos = json.loads(arquivo.read_text())["installed"]
print("\n✅ Autorizado! Coloque isto no seu .env (e nos Secrets do GitHub):\n")
print(f"YT_CLIENT_ID={segredos['client_id']}")
print(f"YT_CLIENT_SECRET={segredos['client_secret']}")
print(f"YT_REFRESH_TOKEN={cred.refresh_token}")
