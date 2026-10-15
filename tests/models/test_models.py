import pytest
from pydantic import ValidationError

from frances.models.bundle import ContentIndex
from frances.models.content import Example


def test_models_forbid_extra() -> None:
    with pytest.raises(ValidationError):
        Example(fr="a", es="b", extra=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Example(fr="a", es="b").fr = "c"  # type: ignore[misc]


def test_content_index_roundtrip() -> None:
    idx = ContentIndex(
        schema_version=1,
        generated_at="2026-10-14T15:20:24.000000Z",
        courses=[],
        topics=[],
        items=[],
        attachments=[],
        cards=[],
        sheets=[],
        voices=[],
        drills=[],
        speech=None,
    )
    assert ContentIndex.model_validate_json(idx.model_dump_json()) == idx
