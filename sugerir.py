"""Gera sugestões de temas com potencial de viralizar e salva em docs/sugestoes.json (o painel mostra)."""
import json
from datetime import datetime

import config
import roteiro

PROMPT = """Você é estrategista de conteúdo para TikTok e YouTube no Brasil.
Nicho do canal: {nicho}
Temas que JÁ foram feitos (não repita): {usados}

Sugira 12 temas de vídeo com alto potencial de busca e de viralizar agora, variados entre si.
Cada tema deve ser específico e curioso (ex: "por que o mar é salgado e os rios não"), não genérico.

Responda SOMENTE com JSON: {{"temas": ["tema 1", "tema 2", "..."]}}"""


def main():
    if not (config.GROQ_API_KEY or config.GEMINI_API_KEY):
        return
    historico = json.loads(config.ARQUIVO_HISTORICO.read_text(encoding="utf-8")) if config.ARQUIVO_HISTORICO.exists() else []
    pedir = roteiro._pedir_ao_groq if config.GROQ_API_KEY else roteiro._pedir_ao_gemini
    dados = pedir(PROMPT.format(nicho=config.NICHO, usados=", ".join(historico[-80:]) or "nenhum"))
    temas = [str(t).strip() for t in dados.get("temas", []) if str(t).strip()][:12]
    destino = config.PASTA / "docs" / "sugestoes.json"
    destino.write_text(json.dumps({"atualizado": datetime.now().astimezone().isoformat(timespec="seconds"),
                                   "temas": temas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"💡 {len(temas)} sugestões de tema salvas")


if __name__ == "__main__":
    main()
