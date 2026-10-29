"""Sonda SPK-06: verifica un proveedor LLM con API compatible con OpenAI.

Lee `LLM_BASE_URL`, `LLM_API_KEY` y `LLM_MODEL` del entorno y hace un POST
`{LLM_BASE_URL}/chat/completions` pidiendo tarjetas con
`response_format = json_schema` estricto. Imprime el código HTTP, la
latencia, el `usage` y si el contenido parsea y cumple el esquema.
Nunca imprime la clave (la enmascara a sus últimos 4 caracteres).

Uso:
    LLM_BASE_URL=https://kiosapi.com/v1 LLM_API_KEY=... LLM_MODEL=... \
        python scripts/spikes/spk06_llm_probe.py [--auth bearer|api-key]

Nota Kiosapi: el gateway está tras Cloudflare y rechaza clientes sin un
User-Agent de navegador (error 1010); por eso se envía siempre uno fijo.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "front_fr": {"type": "string"},
                    "back_es": {"type": "string"},
                },
                "required": ["front_fr", "back_es"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}

USER_TEXT = (
    "Crea 2 tarjetas desde este texto sintético:\n"
    "Les enfants chantent une chanson.\n"
    "Il fait beau en France.\n"
    "Marie lit un livre chaque soir."
)


def mask(key: str) -> str:
    return f"…{key[-4:]}" if len(key) > 4 else "…"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth", choices=("bearer", "api-key"), default="bearer")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not (base_url and api_key and model):
        print("Faltan LLM_BASE_URL, LLM_API_KEY o LLM_MODEL en el entorno.")
        return 2

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Eres un generador de tarjetas de estudio de francés. "
                "Respondes solo con el JSON pedido.",
            },
            {"role": "user", "content": USER_TEXT},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "cards", "strict": True, "schema": SCHEMA},
        },
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if args.auth == "bearer":
        request.add_header("Authorization", f"Bearer {api_key}")
    else:
        request.add_header("api-key", api_key)

    print(f"POST {base_url}/chat/completions model={model} key={mask(api_key)}")
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            status = response.status
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code} en {time.time() - started:.1f}s: {error.read().decode()[:200]}")
        return 1
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Error de red en {time.time() - started:.1f}s: {error}")
        return 1
    elapsed = time.time() - started

    content = body["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
        cards = parsed.get("cards", [])
        valid = (
            isinstance(cards, list)
            and len(cards) > 0
            and all(set(card) == {"front_fr", "back_es"} for card in cards)
        )
    except (json.JSONDecodeError, AttributeError):
        valid = False
    print(f"HTTP {status} en {elapsed:.1f}s usage={body.get('usage')}")
    print(f"json_schema estricto: {'OK' if valid else 'NO CUMPLE'}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
