"""Tests del generador LLM OpenAI-compatible con salida JSON estricta [CRD-04]."""

import json

import httpx
import pytest
import respx

from frances.cards.llm import (
    MAX_INPUT_CHARS,
    SYSTEM_PROMPT,
    LlmGenerator,
    LlmUnavailable,
    llm_from_env,
    render_input,
    strict_schema,
)
from frances.models import GenerationInput, GenerationOutput, TextBlock

BASE = "https://llm.test/v1"
URL = f"{BASE}/chat/completions"

VALID = {
    "cards": [
        {"kind": "vocab", "front_fr": "l'école", "back_es": "la escuela"},
        {"kind": "phrase", "front_fr": "Bonjour à tous", "back_es": "Hola a todos"},
    ],
    "sheet": {
        "summary_es": "Resumen de la publicación.",
        "vocab_fronts": ["l'école"],
        "grammar": [],
        "key_phrases": [],
    },
}

INP = GenerationInput(
    item_id="mt_A",
    title="Leçon 1",
    blocks=[TextBlock(text="Bonjour à tous.", lang="fr", source="sha256:x")],
    input_hash="h",
)


def _ok(payload: dict) -> dict:
    """Respuesta 200 de chat/completions con `payload` como contenido JSON."""
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _inp(blocks: list[tuple[str, str]]) -> GenerationInput:
    """GenerationInput de prueba a partir de pares (lang, texto)."""
    return GenerationInput(
        item_id="i",
        title=None,
        blocks=[TextBlock(text=text, lang=lang, source="s") for lang, text in blocks],
        input_hash="h",
    )


def test_valid_response_returns_output(respx_mock: respx.Router) -> None:
    respx_mock.post(URL).respond(200, json=_ok(VALID))
    out = LlmGenerator(BASE, "k", "m").generate(INP)
    assert isinstance(out, GenerationOutput) and out.cards[0].front_fr == "l'école"


def test_request_shape(respx_mock: respx.Router) -> None:
    respx_mock.post(URL).respond(200, json=_ok(VALID))
    LlmGenerator(BASE, "k", "m").generate(INP)
    body = json.loads(respx_mock.calls[0].request.content)
    assert body["model"] == "m" and body["temperature"] == 0.2
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "generation_output"
    assert rf["json_schema"]["strict"] is True


def test_invalid_then_valid_retries_once_with_error(respx_mock: respx.Router) -> None:
    respx_mock.post(URL).mock(
        side_effect=[
            httpx.Response(200, json=_ok({"cards": 1})),
            httpx.Response(200, json=_ok(VALID)),
        ]
    )
    LlmGenerator(BASE, "k", "m").generate(INP)
    last = json.loads(respx_mock.calls[1].request.content)["messages"][-1]
    assert last["role"] == "user" and "no cumple el esquema" in last["content"]


def test_invalid_json_twice_raises(respx_mock: respx.Router) -> None:
    respx_mock.post(URL).respond(200, json={"choices": [{"message": {"content": "no json"}}]})
    with pytest.raises(LlmUnavailable):
        LlmGenerator(BASE, "k", "m").generate(INP)
    assert len(respx_mock.calls) == 2  # un solo reintento


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_error_raises(respx_mock: respx.Router, status: int) -> None:
    respx_mock.post(URL).respond(status, json={"error": {"message": "upstream"}})
    with pytest.raises(LlmUnavailable):
        LlmGenerator(BASE, "k", "m").generate(INP)
    assert len(respx_mock.calls) == 1  # sin reintento


def test_timeout_raises(respx_mock: respx.Router) -> None:
    respx_mock.post(URL).mock(side_effect=httpx.ReadTimeout("read timed out"))
    with pytest.raises(LlmUnavailable):
        LlmGenerator(BASE, "k", "m").generate(INP)
    assert len(respx_mock.calls) == 1


def test_drill_cards_dropped_and_caps_applied(respx_mock: respx.Router) -> None:
    payload = {
        "cards": [
            *[{"kind": "vocab", "front_fr": f"mot {i}", "back_es": str(i)} for i in range(30)],
            *[{"kind": "phrase", "front_fr": f"phrase {i}", "back_es": "p"} for i in range(12)],
            {"kind": "drill", "front_fr": "drill", "back_es": "drill"},
        ],
        "sheet": {
            "summary_es": "s",
            "vocab_fronts": [],
            "grammar": [
                {"title": f"punto {i}", "explanation_es": "e", "examples": []} for i in range(7)
            ],
            "key_phrases": [],
        },
    }
    respx_mock.post(URL).respond(200, json=_ok(payload))
    out = LlmGenerator(BASE, "k", "m").generate(INP)
    kinds = [card.kind for card in out.cards]
    assert "drill" not in kinds
    assert sum(kind == "vocab" for kind in kinds) == 25
    assert sum(kind == "phrase" for kind in kinds) == 10
    assert len(out.sheet.grammar) == 5


def test_render_input_truncates_prioritizing_fr() -> None:
    s = render_input(_inp([("es", "e" * 9000), ("fr", "f" * 9000)]))
    assert len(s) <= MAX_INPUT_CHARS and s.count("f") > s.count("e")


def test_strict_schema_requires_all_properties() -> None:
    card = strict_schema()["$defs"]["CardDraft"]
    assert set(card["required"]) == set(card["properties"]) and card["additionalProperties"] is False


def test_llm_from_env() -> None:
    assert (
        llm_from_env({"LLM_BASE_URL": BASE, "LLM_API_KEY": "k"}) is None
        and llm_from_env({"LLM_BASE_URL": BASE, "LLM_API_KEY": "k", "LLM_MODEL": "m"}) is not None
    )
