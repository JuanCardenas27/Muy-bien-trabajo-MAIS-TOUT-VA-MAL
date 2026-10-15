"""Extracción de texto de PDF con fallback a OCR por página (Task EXT-01)."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image


@dataclass
class PageText:
    page: int
    text: str
    method: Literal["pdf_text", "pdf_ocr"]


def extract_pdf(
    path: Path,
    ocr: Callable[[Image.Image], str],
    min_chars: int = 40,
    dpi: int = 200,
) -> list[PageText]:
    """Extrae el texto de cada página: capa de texto si basta, si no OCR."""
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    pages: list[PageText] = []
    doc = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(doc)):
            page = doc[index]
            try:
                textpage = page.get_textpage()
                try:
                    raw = textpage.get_text_range()
                finally:
                    textpage.close()
                useful = sum(1 for ch in raw if not ch.isspace())
                if useful >= min_chars:
                    pages.append(PageText(page=index + 1, text=raw, method="pdf_text"))
                else:
                    image = page.render(scale=dpi / 72).to_pil()
                    pages.append(PageText(page=index + 1, text=ocr(image), method="pdf_ocr"))
            finally:
                page.close()
    finally:
        doc.close()
    return pages
