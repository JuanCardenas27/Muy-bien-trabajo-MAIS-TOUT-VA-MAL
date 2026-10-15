"""OCR de imágenes fra+spa (Task EXT-02)."""

import re
import shutil
import unicodedata
from pathlib import Path

import pytest
from PIL import Image

from frances.extract.ocr import ocr_file, preprocess, tesseract_version

FIX = Path(__file__).resolve().parent.parent / "fixtures"

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract")


def fold(s: str) -> str:
    """Minúsculas sin marcas combinantes (compara sin tildes/diacríticos)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c)
    )


def test_preprocess_grayscale_and_upscale() -> None:
    out = preprocess(Image.new("RGB", (500, 100), "white"))
    assert out.mode == "L" and out.size == (1000, 200)
    assert preprocess(Image.new("RGB", (1200, 100))).size == (1200, 100)


@needs_tesseract
def test_ocr_file_reads_french_fixture() -> None:
    text = fold(ocr_file(FIX / "images/phrase.png"))  # FND-05: «Les enfants chantent une chanson.»
    assert "enfants" in text and "chanson" in text


@needs_tesseract
def test_tesseract_version_is_semver_like() -> None:
    assert re.match(r"^\d+\.\d+", tesseract_version())
