"""Tests de la etapa cards: upgrade a LLM, fallback, cuotas y errores (CRD-05)."""

import sqlite3

from frances.cards.run import run_cards_with

from frances.cards.llm import LlmUnavailable
from frances.cards.rules import PENDING_NOTE, RulesGenerator
from frances.db.usage import current_month, usage_get
from frances.models import CardDraft, GenerationInput, GenerationOutput, SheetDraft
from frances.stage import StageContext
from tests.cards.conftest import SEED_SHA


class FakeTranslator:
    """Traductor de prueba: prefija `ES:` y registra los lotes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, texts: list[str], src: str = "fr", dst: str = "es") -> list[str | None]:
        self.calls.append(list(texts))
        return ["ES:" + text for text in texts]


class NoneTranslator:
    """Traductor sin cuota: todo queda pendiente."""

    def translate(self, texts: list[str], src: str = "fr", dst: str = "es") -> list[str | None]:
        return [None] * len(texts)


def _out(*fronts: str) -> GenerationOutput:
    """Salida mínima con las tarjetas vocab indicadas."""
    return GenerationOutput(
        cards=[CardDraft(kind="vocab", front_fr=front, back_es="ES:" + front) for front in fronts],
        sheet=SheetDraft(
            summary_es="resumen",
            vocab_fronts=list(fronts),
            grammar=[],
            key_phrases=[],
        ),
    )


class FakeLlm:
    """Generador LLM de prueba; `fail=True` simula el proveedor caído."""

    name = "llm"
    version = "1"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def generate(self, inp: GenerationInput) -> GenerationOutput:
        if self.fail:
            raise LlmUnavailable("llm caído")
        return _out("le pain")


RULES = RulesGenerator(FakeTranslator())


def _generations(ctx: StageContext) -> list[dict[str, object]]:
    """Filas de `generations` como dicts, ordenadas por ítem."""
    ctx.store.conn.row_factory = sqlite3.Row
    rows = ctx.store.conn.execute(
        "SELECT item_id, generator FROM generations ORDER BY item_id"
    ).fetchall()
    return [dict(row) for row in rows]


def _pending(ctx: StageContext) -> int:
    """Tarjetas con traducción pendiente."""
    row = ctx.store.conn.execute(
        "SELECT COUNT(*) FROM cards WHERE back_es = '' AND notes = ?", (PENDING_NOTE,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def _add_item(ctx: StageContext, item_id: str, classroom_id: str, seen: str) -> None:
    """Inserta una publicación viva extra para probar la cuota diaria."""
    row = ctx.store.conn.execute("SELECT id FROM courses").fetchone()
    assert row is not None
    ctx.store.conn.execute(
        "INSERT INTO items (id, course_id, kind, classroom_id, title, text, state,"
        " creation_time, update_time, content_hash, raw_json, first_seen_at, last_seen_at)"
        " VALUES (?, ?, 'material', ?, 'Leçon 3', 'Merci beaucoup.', 'PUBLISHED',"
        " ?, ?, ?, '{}', ?, ?)",
        (item_id, str(row[0]), classroom_id, seen, seen, f"{item_id}-content", seen, seen),
    )


def test_rules_upgraded_to_llm_when_available(ctx: StageContext) -> None:
    run_cards_with(ctx, RULES, None, FakeTranslator())
    run_cards_with(ctx, RULES, FakeLlm(), FakeTranslator())

    assert {generation["generator"] for generation in _generations(ctx)} == {"llm"}


def test_llm_failure_falls_back_to_rules(ctx: StageContext) -> None:
    report = run_cards_with(ctx, RULES, FakeLlm(fail=True), FakeTranslator())

    assert report.status == "ok"
    assert report.counts["cards.llm_fallback"] >= 1
    assert {generation["generator"] for generation in _generations(ctx)} == {"rules"}


def test_pending_translation_retried(ctx: StageContext) -> None:
    run_cards_with(ctx, RulesGenerator(NoneTranslator()), None, NoneTranslator())
    assert _pending(ctx) > 0

    report = run_cards_with(ctx, RULES, None, FakeTranslator())

    assert report.counts["cards.retranslated"] > 0
    assert _pending(ctx) == 0


def test_llm_daily_limit(ctx: StageContext) -> None:
    _add_item(ctx, "mt_C", "c-1", "2026-10-03T10:00:00Z")
    ctx.settings.cards.llm_daily_item_limit = 2

    run_cards_with(ctx, RULES, FakeLlm(), FakeTranslator())

    assert sorted(str(generation["generator"]) for generation in _generations(ctx)) == [
        "llm",
        "llm",
        "rules",
    ]
    assert usage_get(ctx.store.conn, current_month(ctx.now()), "llm_items") == 2


def test_unchanged_item_not_regenerated(ctx: StageContext) -> None:
    first = run_cards_with(ctx, RULES, None, FakeTranslator())
    second = run_cards_with(ctx, RULES, None, FakeTranslator())

    assert first.counts["cards.generated"] > 0
    assert second.counts["cards.generated"] == 0


def test_item_error_is_partial(ctx: StageContext) -> None:
    ctx.paths.extraction_path(SEED_SHA, "1").write_text("no es json", encoding="utf-8")

    report = run_cards_with(ctx, RULES, None, FakeTranslator())

    assert report.status == "partial"
    assert report.errors
    assert [generation["item_id"] for generation in _generations(ctx)] == ["mt_B"]
