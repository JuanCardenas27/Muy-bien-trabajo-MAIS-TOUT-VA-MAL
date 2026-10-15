"""Contratos de extracción y generación de tarjetas (plan maestro)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["fr", "es", "en", "mixed", "unknown"]
CardKind = Literal["vocab", "phrase", "grammar", "conjugation", "drill"]
ExtractMethod = Literal["pdf_text", "pdf_ocr", "image_ocr", "export_text", "plain"]


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    lang: Lang
    source: str
    page: int | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    blob_sha256: str
    extractor_version: str
    method: ExtractMethod
    blocks: list[TextBlock]
    char_count: int


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fr: str
    es: str


class GrammarPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    explanation_es: str
    examples: list[Example]


class CardDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CardKind
    front_fr: str
    back_es: str
    example_fr: str | None = None
    example_es: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SheetDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary_es: str
    vocab_fronts: list[str]
    grammar: list[GrammarPoint]
    key_phrases: list[Example]


class StudySheet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    summary_es: str
    vocab_card_ids: list[str]
    grammar: list[GrammarPoint]
    key_phrases: list[Example]


class GenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    title: str | None
    blocks: list[TextBlock]
    input_hash: str


class GenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cards: list[CardDraft]
    sheet: SheetDraft
