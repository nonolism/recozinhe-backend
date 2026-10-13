"""
Descobre quais modelos do Gemini estão respondendo AGORA com a sua chave.

Como usar (na pasta recozinhe-backend, com o venv ativado):

    python verificar_gemini.py

Ele lista os modelos "flash" que a sua chave pode usar e manda uma pergunta
curtinha para cada um (gasta quase nada da cota). No fim, sugere o que colocar
no arquivo .env.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Biblioteca google-genai não instalada. Rode: pip install -r requirements.txt")
    sys.exit(1)

API_KEY = os.getenv("GEMINI_API_KEY", "")
if not API_KEY:
    print("GEMINI_API_KEY não encontrada no arquivo .env.")
    sys.exit(1)

# Sem repetições automáticas: queremos saber rápido se o modelo responde
client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))

IGNORAR = ("tts", "live", "image", "embedding", "audio", "transcribe", "translate", "native")

print("Buscando os modelos disponíveis para a sua chave...\n")
try:
    modelos = [
        m.name.replace("models/", "")
        for m in client.models.list()
        if "generateContent" in (m.supported_actions or [])
        and "flash" in m.name
        and not any(palavra in m.name for palavra in IGNORAR)
    ]
except Exception as erro:
    print(f"Não consegui listar os modelos: {str(erro)[:300]}")
    sys.exit(1)

funcionando = []
for modelo in modelos:
    try:
        resposta = client.models.generate_content(
            model=modelo,
            contents="Responda apenas com a palavra: ok",
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        print(f"  OK      {modelo}  ->  {(resposta.text or '').strip()[:20]}")
        funcionando.append(modelo)
    except Exception as erro:
        texto = str(erro)
        if "503" in texto:
            motivo = "sobrecarregado (503)"
        elif "429" in texto:
            motivo = "sem cota gratuita (429)"
        elif "404" in texto:
            motivo = "não disponível (404)"
        else:
            motivo = texto[:80]
        print(f"  FALHOU  {modelo}  ->  {motivo}")

print()
if funcionando:
    print("Coloque isto no seu arquivo .env e reinicie o backend:\n")
    print(f"GEMINI_MODEL={funcionando[0]}")
    if len(funcionando) > 1:
        print(f"GEMINI_FALLBACK_MODELS={','.join(funcionando[1:4])}")
else:
    print("Nenhum modelo respondeu agora. Normalmente é sobrecarga temporária do Google:")
    print("espere alguns minutos e rode este script de novo.")
