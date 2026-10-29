"""Generador LLM OpenAI-compatible con salida JSON estricta validada [CRD-04].

Contrato del proveedor en ``docs/decisions/ADR-006-llm.md``: POST a
``{LLM_BASE_URL}/chat/completions`` con ``Authorization: Bearer`` y un
``User-Agent`` de navegador fijo (el gateway está tras Cloudflare y rechaza
clientes sin él). La respuesta se valida contra :class:`GenerationOutput`;
si no cumple el esquema se hace un único reintento con el error como pista.
"""

import json
from collections.abc import Mapping
from typing import Any

import httpx

from frances.log import get_logger, redact
from frances.models.content import CardDraft, GenerationInput, GenerationOutput

#: Presupuesto máximo de caracteres que se envía en el mensaje de usuario.
MAX_INPUT_CHARS = 12_000

#: Recortes post-validación (plan CRD-04).
MAX_VOCAB = 25
MAX_PHRASES = 10
MAX_GRAMMAR_POINTS = 5

_TEMPERATURE = 0.2
_TIMEOUT_S = 30.0
_MAX_ERROR_CHARS = 1000
_SCHEMA_NAME = "generation_output"

#: ADR-006: UA de navegador fijo; Cloudflare responde 1010 sin él.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

#: Texto fijado por el plan CRD-04 (copy exacta; no parafrasear). El guion de
#: «A1-A2» va escapado para no disparar RUF001: el valor en tiempo de
#: ejecución es idéntico al del plan.
SYSTEM_PROMPT = (
    "Eres un asistente que prepara material de estudio de francés para un estudiante "
    "universitario hispanohablante de nivel A1\u2013A2.\n"
    "Recibes una publicación de su profesora: un título y bloques de texto etiquetados "
    "con su idioma ([fr], [es], [mixed]).\n"
    "Devuelve solo un objeto JSON que cumpla el esquema generation_output. No escribas "
    "nada fuera del JSON.\n"
    "Reglas:\n"
    "1. Usa únicamente palabras, frases y temas que aparecen en el texto. Jamás inventes "
    "contenido que no esté en el texto.\n"
    '2. Tarjetas "vocab": máximo 25. front_fr es la palabra en forma de diccionario; '
    "los sustantivos llevan artículo (le, la, l', les). back_es es su traducción al "
    "español.\n"
    '3. Tarjetas "phrase": máximo 10 frases útiles copiadas del texto, de 3 a 14 '
    "palabras, con su traducción en back_es.\n"
    '4. Tarjetas "grammar" o "conjugation" solo si el texto trabaja ese punto: front_fr '
    "nombra la estructura en francés y back_es la explica en español en una o dos "
    "oraciones.\n"
    "5. Si una oración del texto usa la palabra, ponla en example_fr y su traducción en "
    "example_es; si no, déjalos en null.\n"
    '6. Nunca crees tarjetas de tipo "drill".\n'
    "7. Ficha (sheet): summary_es resume la publicación en español en 2 a 4 oraciones.\n"
    "8. vocab_fronts repite exactamente el front_fr de las tarjetas vocab más "
    "importantes.\n"
    "9. grammar tiene máximo 5 puntos; cada uno con título, explicación en español y "
    "exactamente 2 ejemplos (fr y es) tomados o adaptados del texto.\n"
    "10. key_phrases repite las frases útiles con su traducción.\n"
    "11. Conserva la ortografía francesa (tildes, cedillas, apóstrofos) tal como "
    "aparece en el texto.\n"
    "12. tags: como máximo 3 etiquetas cortas en español y en minúsculas, por ejemplo "
    '"saludos" o "familia".\n'
    "13. Si el texto no contiene francés, devuelve listas vacías y un resumen breve en "
    "español.\n"
    "Escribe todas las traducciones y explicaciones en español neutro, claras y breves."
)

_META_KEYS = ("default", "title", "description")
_LANG_PRIORITY = {"fr": 0, "mixed": 1}
_CARD_CAPS = {"vocab": MAX_VOCAB, "phrase": MAX_PHRASES}

_logger = get_logger(__name__)


class LlmUnavailable(Exception):
    """El LLM no respondió o no devolvió un JSON válido tras el reintento."""


def render_input(inp: GenerationInput) -> str:
    """Título y bloques ``[lang] texto``, con ``fr`` y ``mixed`` primero.

    Los grupos conservan su orden original. Si el resultado supera
    :data:`MAX_INPUT_CHARS`, se corta el último bloque incluido para no
    superar el presupuesto.
    """
    blocks = sorted(inp.blocks, key=lambda block: _LANG_PRIORITY.get(block.lang, 2))
    chunks: list[str] = []
    if inp.title:
        chunks.append(f"Título: {inp.title}")
    chunks.extend(f"[{block.lang}] {block.text.strip()}" for block in blocks)

    parts: list[str] = []
    remaining = MAX_INPUT_CHARS
    for chunk in chunks:
        separator = 1 if parts else 0
        available = remaining - separator
        if available <= 0:
            break
        if len(chunk) <= available:
            parts.append(chunk)
            remaining -= len(chunk) + separator
        else:
            parts.append(chunk[:available])
            remaining = 0
    return "\n".join(parts)


def _accepts_null(prop: dict[str, Any]) -> bool:
    """True si el subesquema ya admite ``null``."""
    if prop.get("type") == "null":
        return True
    branches = prop.get("anyOf")
    return isinstance(branches, list) and any(
        isinstance(branch, dict) and branch.get("type") == "null" for branch in branches
    )


def _allow_null(prop: dict[str, Any]) -> None:
    """Amplía la propiedad para que admita ``null`` conservando metadatos."""
    if _accepts_null(prop):
        return
    meta = {key: prop[key] for key in _META_KEYS if key in prop}
    branch = {key: value for key, value in prop.items() if key not in _META_KEYS}
    prop.clear()
    prop.update(meta)
    prop["anyOf"] = [branch, {"type": "null"}]


def _enforce_strict(node: Any) -> None:
    """Cierra cada objeto del esquema: todo ``required`` y sin extras."""
    if isinstance(node, list):
        for item in node:
            _enforce_strict(item)
        return
    if not isinstance(node, dict) or "$ref" in node:
        return
    properties = node.get("properties")
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and "default" in prop:
                _allow_null(prop)
            _enforce_strict(prop)
        node["required"] = list(properties)
        node["additionalProperties"] = False
    for key in list(node):
        if key in ("properties", "required", "additionalProperties"):
            continue
        _enforce_strict(node[key])


def strict_schema() -> dict[str, Any]:
    """Esquema JSON de :class:`GenerationOutput` apto para ``strict: true``.

    Parte de ``GenerationOutput.model_json_schema()`` y, en cada objeto,
    requiere todas las propiedades, prohíbe las extra y permite ``null`` en
    las que tenían un valor por defecto.
    """
    schema = GenerationOutput.model_json_schema()
    defs = schema.get("$defs")
    if isinstance(defs, dict):
        for definition in defs.values():
            _enforce_strict(definition)
    _enforce_strict(schema)
    return schema


def _array_branch(schema: dict[str, Any]) -> dict[str, Any] | None:
    """Rama de tipo array del esquema (directa o dentro de un ``anyOf``)."""
    if schema.get("type") == "array":
        return schema
    branches = schema.get("anyOf")
    if isinstance(branches, list):
        for branch in branches:
            if isinstance(branch, dict) and branch.get("type") == "array":
                return branch
    return None


def _normalize_null_lists(value: Any, schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Convierte ``null`` en propiedades de tipo array a ``[]`` antes de validar."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        target = defs.get(ref.rsplit("/", 1)[-1])
        if isinstance(target, dict):
            return _normalize_null_lists(value, target, defs)
        return value
    if value is None:
        return [] if _array_branch(schema) is not None else None
    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return {
                key: _normalize_null_lists(item, properties[key], defs)
                if key in properties and isinstance(properties[key], dict)
                else item
                for key, item in value.items()
            }
        return value
    if isinstance(value, list):
        array = _array_branch(schema)
        items = array.get("items") if array is not None else None
        if isinstance(items, dict):
            return [_normalize_null_lists(item, items, defs) for item in value]
        return value
    return value


def _parse_output(content: str) -> GenerationOutput:
    """Parsea y valida el contenido; ``ValueError`` si no cumple el esquema."""
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    schema = strict_schema()
    defs = schema.get("$defs")
    normalized = _normalize_null_lists(data, schema, defs if isinstance(defs, dict) else {})
    return GenerationOutput.model_validate_json(json.dumps(normalized))


def _apply_caps(output: GenerationOutput) -> GenerationOutput:
    """Descarta tarjetas ``drill`` y aplica los topes del plan."""
    counts: dict[str, int] = {}
    kept: list[CardDraft] = []
    for card in output.cards:
        if card.kind == "drill":
            continue
        cap = _CARD_CAPS.get(card.kind)
        if cap is not None:
            used = counts.get(card.kind, 0)
            if used >= cap:
                continue
            counts[card.kind] = used + 1
        kept.append(card)
    sheet = output.sheet
    if len(sheet.grammar) > MAX_GRAMMAR_POINTS:
        sheet = sheet.model_copy(update={"grammar": sheet.grammar[:MAX_GRAMMAR_POINTS]})
    return GenerationOutput(cards=kept, sheet=sheet)


def _extract_content(response: httpx.Response) -> str:
    """Saca ``choices[0].message.content``; ``LlmUnavailable`` si no está."""
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        _logger.warning("llm respuesta inesperada: %s", redact(response.text))
        raise LlmUnavailable("respuesta inesperada del LLM") from exc
    if not isinstance(content, str):
        _logger.warning("llm contenido no textual: %s", redact(response.text))
        raise LlmUnavailable("contenido no textual del LLM")
    return content


class LlmGenerator:
    """Cliente ``chat/completions`` con salida JSON validada."""

    name = "llm"
    version = "1"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        # trust_env=False: sin proxies del entorno ni red en tests (R-02).
        self._client = client if client is not None else httpx.Client(trust_env=False)

    def _headers(self) -> dict[str, str]:
        # ADR-006 eligió Bearer; `api-key` se mantiene por el contrato del plan.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "api-key": self._api_key,
            "User-Agent": USER_AGENT,
        }

    def _complete(self, messages: list[dict[str, str]]) -> str:
        """POST del turno completo; ``LlmUnavailable`` en cualquier fallo."""
        body = {
            "model": self._model,
            "temperature": _TEMPERATURE,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _SCHEMA_NAME,
                    "strict": True,
                    "schema": strict_schema(),
                },
            },
        }
        try:
            response = self._client.post(
                self._url,
                json=body,
                headers=self._headers(),
                timeout=_TIMEOUT_S,
            )
        except httpx.TimeoutException as exc:
            _logger.warning("llm timeout: %s", redact(str(exc)))
            raise LlmUnavailable("timeout del LLM") from exc
        except httpx.HTTPError as exc:
            _logger.warning("llm error de red: %s", redact(str(exc)))
            raise LlmUnavailable("error de red con el LLM") from exc
        if response.status_code != 200:
            _logger.warning("llm fallo %s: %s", response.status_code, redact(response.text))
            raise LlmUnavailable(f"el LLM respondió HTTP {response.status_code}")
        return _extract_content(response)

    def generate(self, inp: GenerationInput) -> GenerationOutput:
        """Genera y valida; un único reintento con el error de esquema."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_input(inp)},
        ]
        content = self._complete(messages)
        try:
            return _apply_caps(_parse_output(content))
        except ValueError as exc:
            problem = str(exc)[:_MAX_ERROR_CHARS]
            _logger.info("llm respuesta inválida, reintento único: %s", redact(problem))
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"La respuesta no cumple el esquema: {problem}. "
                    "Devuelve solo el JSON corregido."
                ),
            }
        )
        content = self._complete(messages)
        try:
            return _apply_caps(_parse_output(content))
        except ValueError as exc:
            raise LlmUnavailable("el LLM no devolvió un JSON válido tras el reintento") from exc


def llm_from_env(env: Mapping[str, str]) -> LlmGenerator | None:
    """``None`` si falta ``LLM_BASE_URL``, ``LLM_API_KEY`` o ``LLM_MODEL``."""
    base_url = env.get("LLM_BASE_URL")
    api_key = env.get("LLM_API_KEY")
    model = env.get("LLM_MODEL")
    if not base_url or not api_key or not model:
        return None
    return LlmGenerator(base_url, api_key, model)
