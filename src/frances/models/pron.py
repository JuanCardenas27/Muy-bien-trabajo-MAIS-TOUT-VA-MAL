"""Contratos de pronunciación (plan maestro)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ErrorType = Literal[
    "None",
    "Omission",
    "Insertion",
    "Mispronunciation",
    "UnexpectedBreak",
    "MissingBreak",
    "Monotone",
]


class PhonemeScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phoneme: str
    accuracy: float


class WordScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    word: str
    accuracy: float
    error_type: ErrorType
    phonemes: list[PhonemeScore]


class PronScores(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pron: float
    accuracy: float
    fluency: float
    completeness: float


class PronResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    card_id: str | None
    reference_text: str
    recognized_text: str
    at: str
    duration_ms: int
    scores: PronScores
    words: list[WordScore]
