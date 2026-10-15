"""Generador de tarjetas por reglas: spaCy + Translator inyectado (CRD-02).

Siempre disponible (sin red ni LLM): extrae vocabulario y frases del texto
francés con ``fr_core_news_sm`` y traduce en un solo lote con el
``Translator`` inyectado. Las traducciones ``None`` (cuota agotada) quedan
marcadas con :data:`PENDING_NOTE` para que CRD-05 las reintente.
"""

from typing import Protocol

import spacy
from spacy.language import Language

from frances.models.content import (
    CardDraft,
    Example,
    GenerationInput,
    GenerationOutput,
    SheetDraft,
)
from frances.textnorm import display_clean

#: Nota de las tarjetas cuya traducción quedó pendiente (la usa CRD-05).
PENDING_NOTE = "traducción pendiente"

_VOCAB_POS = frozenset({"NOUN", "VERB", "ADJ", "ADV"})
#: Iniciales que piden elisión (vocales, incluida la h muda/aspirada).
_ELISION_STARTS = frozenset("aeiouyàâäéèêëîïôöùûüÿæœh")
_MAX_PHRASES = 10

_nlp_cache: Language | None = None


def _load_nlp() -> Language:
    """Carga ``fr_core_news_sm`` una sola vez (caché a nivel de módulo)."""
    global _nlp_cache
    if _nlp_cache is None:
        _nlp_cache = spacy.load("fr_core_news_sm")
    return _nlp_cache


class Translator(Protocol):
    """Traduce un lote de textos; ``None`` = cuota agotada para ese texto."""

    def translate(self, texts: list[str], src: str = "fr", dst: str = "es") -> list[str | None]: ...


class CardGenerator(Protocol):
    """Generador intercambiable de tarjetas (``rules`` | ``llm``)."""

    name: str
    version: str

    def generate(self, inp: GenerationInput) -> GenerationOutput: ...


def _noun_front(lemma: str, surface: str, gender: str, number: str) -> str:
    """Artículo + forma de diccionario según la morfología del token."""
    if lemma.casefold()[:1] in _ELISION_STARTS:
        return "l'" + lemma
    if gender == "Masc":
        return "le " + lemma
    if gender == "Fem":
        return "la " + lemma
    if number == "Plur" and lemma.casefold() == surface.casefold():
        return "les " + lemma
    return lemma


class RulesGenerator:
    """Generador por reglas (spaCy) con ``Translator`` inyectado."""

    name = "rules"
    version = "1"

    def __init__(
        self,
        translator: Translator,
        nlp: Language | None = None,
        vocab_max: int = 25,
    ) -> None:
        self._translator = translator
        self._nlp = nlp
        self._vocab_max = vocab_max

    def generate(self, inp: GenerationInput) -> GenerationOutput:
        nlp = self._nlp if self._nlp is not None else _load_nlp()
        fr_texts = [b.text for b in inp.blocks if b.lang in ("fr", "mixed")]

        freq: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        front_of: dict[str, str] = {}
        sentences: list[tuple[str, set[str], int, bool]] = []
        order = 0
        for text in fr_texts:
            doc = nlp(text)
            for sent in doc.sents:
                lemmas: set[str] = set()
                n_tokens = 0
                has_propn = False
                for tok in sent:
                    if tok.is_space:
                        continue
                    n_tokens += 1
                    if tok.pos_ == "PROPN":
                        has_propn = True
                    if tok.is_punct:
                        continue
                    # PROPN nunca entra: no está en _VOCAB_POS.
                    if tok.pos_ not in _VOCAB_POS or tok.is_stop:
                        continue
                    lemma = tok.lemma_
                    if len(lemma) < 3:
                        continue
                    lemmas.add(lemma)
                    freq[lemma] = freq.get(lemma, 0) + 1
                    if lemma not in first_seen:
                        first_seen[lemma] = order
                        order += 1
                        if tok.pos_ == "NOUN":
                            gender = tok.morph.get("Gender", [])
                            number = tok.morph.get("Number", [])
                            front_of[lemma] = _noun_front(
                                lemma,
                                tok.text,
                                gender[0] if gender else "",
                                number[0] if number else "",
                            )
                        else:
                            front_of[lemma] = lemma
                sentences.append((display_clean(sent.text), lemmas, n_tokens, has_propn))

        ranked = sorted(freq, key=lambda lemma: (-freq[lemma], first_seen[lemma]))
        vocab_lemmas = ranked[: self._vocab_max]
        vocab_fronts = [front_of[lemma] for lemma in vocab_lemmas]
        vocab_set = set(vocab_lemmas)

        # Las oraciones con nombres propios no dan frases (test_no_proper_nouns).
        phrase_fronts = [
            text
            for text, lemmas, n_tokens, has_propn in sentences
            if 3 <= n_tokens <= 14 and lemmas & vocab_set and not has_propn
        ][:_MAX_PHRASES]

        summary = " ".join(text for text, _, _, _ in sentences[:3] if text)

        batch = [*vocab_fronts, *phrase_fronts]
        if summary:
            batch.append(summary)
        translated: list[str | None] = self._translator.translate(batch) if batch else []

        cards: list[CardDraft] = []
        for front, back in zip(vocab_fronts, translated[: len(vocab_fronts)], strict=False):
            cards.append(
                CardDraft(
                    kind="vocab",
                    front_fr=front,
                    back_es=back if back is not None else "",
                    notes=None if back is not None else PENDING_NOTE,
                )
            )
        phrase_backs = translated[len(vocab_fronts) : len(vocab_fronts) + len(phrase_fronts)]
        for front, back in zip(phrase_fronts, phrase_backs, strict=False):
            cards.append(
                CardDraft(
                    kind="phrase",
                    front_fr=front,
                    back_es=back if back is not None else "",
                    notes=None if back is not None else PENDING_NOTE,
                )
            )

        summary_back = translated[-1] if summary and translated else None
        summary_es = summary_back if summary_back is not None else ""
        sheet = SheetDraft(
            summary_es=summary_es,
            vocab_fronts=list(vocab_fronts),
            grammar=[],
            key_phrases=[
                Example(fr=front, es=card.back_es or "")
                for front, card in zip(phrase_fronts, cards[len(vocab_fronts) :], strict=False)
            ],
        )
        return GenerationOutput(cards=cards, sheet=sheet)
