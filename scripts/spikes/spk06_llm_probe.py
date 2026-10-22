"""SPK-06: sonda de un proveedor LLM con API compatible con OpenAI.

Hace un POST a `{LLM_BASE_URL}/chat/completions` con `response_format`
`json_schema` estricto (esquema mínimo tipo CardDraft) e imprime el código
HTTP, la latencia, `usage` y si el contenido parsea y cumple el esquema.
Nunca imprime la clave: se enmascara todo menos los últimos 4 caracteres.

Solo stdlib. Uso (plan 2026-10-14-01, Task SPK-06):
  LLM_BASE_URL=https://api.ejemplo.com/v1 LLM_API_KEY=... LLM_MODEL=modelo \\
    python scripts/spikes/spk06_llm_probe.py --auth bearer
  ... --auth api-key
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

SYSTEM = (
    "Eres un asistente que prepara tarjetas de estudio de francés para un "
    "hispanohablante. Devuelve solo un objeto JSON que cumpla el esquema cards."
)
USER = (
    "[fr] Bonjour, je m'appelle Léa.\n"
    "[fr] J'habite à Lyon avec ma famille.\n"
    "[fr] Le week-end, nous allons au marché."
)
SCHEMA: dict[str, Any] = {
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


def mask(secret: str) -> str:
    if len(secret) <= 4:
        return "*" * len(secret)
    return "*" * (len(secret) - 4) + secret[-4:]


def validate(payload: Any) -> str | None:
    """Devuelve None si `payload` cumple SCHEMA, si no el motivo."""
    if not isinstance(payload, dict) or set(payload) != {"cards"}:
        return "el objeto raíz debe tener exactamente la clave 'cards'"
    cards = payload["cards"]
    if not isinstance(cards, list):
        return "'cards' debe ser una lista"
    for i, card in enumerate(cards):
        if not isinstance(card, dict) or set(card) != {"front_fr", "back_es"}:
            return f"cards[{i}] debe tener exactamente front_fr y back_es"
        if not all(isinstance(card[k], str) for k in ("front_fr", "back_es")):
            return f"cards[{i}] tiene valores que no son texto"
    return None


def build_request(base_url: str, api_key: str, model: str, auth: str) -> urllib.request.Request:
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "cards", "strict": True, "schema": SCHEMA},
        },
    }
    headers = {"Content-Type": "application/json"}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["api-key"] = api_key
    return urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--auth", choices=["bearer", "api-key"], default="bearer")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    env = {"LLM_BASE_URL": base_url, "LLM_API_KEY": api_key, "LLM_MODEL": model}
    missing = [name for name, value in env.items() if not value]
    if missing:
        print(f"Faltan variables de entorno: {', '.join(missing)}", file=sys.stderr)
        return 2

    print(f"endpoint: {base_url.rstrip('/')}/chat/completions")
    print(f"modelo:   {model}")
    print(f"auth:     {args.auth} (clave {mask(api_key)})")

    req = build_request(base_url, api_key, model, args.auth)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"error de red: {exc}")
        return 1
    latency_ms = (time.monotonic() - start) * 1000

    print(f"HTTP:     {status}")
    print(f"latencia: {latency_ms:.0f} ms")
    raw = raw.replace(api_key, mask(api_key))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"respuesta no es JSON: {raw[:500]}")
        return 1
    if status != 200:
        print(f"error:    {json.dumps(data, ensure_ascii=False)[:1000]}")
        return 1

    print(f"usage:    {json.dumps(data.get('usage'), ensure_ascii=False)}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("respuesta sin choices[0].message.content")
        return 1
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        print(f"contenido NO parsea como JSON: {str(content)[:500]}")
        return 1
    problem = validate(payload)
    if problem:
        print(f"contenido parsea pero NO cumple el esquema: {problem}")
        return 1
    print(f"OK: JSON válido contra el esquema strict ({len(payload['cards'])} tarjetas)")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
