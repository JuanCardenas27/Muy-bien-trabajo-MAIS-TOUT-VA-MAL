"""Tests de extracción de PDF (Task EXT-01)."""

from pathlib import Path

from PIL import Image

from frances.extract.pdf import extract_pdf

FIX = Path(__file__).resolve().parent.parent / "fixtures"


class CountingOcr:
    """Doble de OCR que cuenta llamadas y guarda las imágenes recibidas."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.images: list[Image.Image] = []

    def __call__(self, img: Image.Image) -> str:
        self.calls += 1
        self.images.append(img)
        return self.text


def n_pages(path: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def page_width_pt(path: Path) -> float:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        w, _ = doc[0].get_size()
        return float(w)
    finally:
        doc.close()


def two_page_pdf(tmp_path: Path, first: str, second: str) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "two-pages.pdf"
    doc = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    doc.drawString(72, A4[1] - 72, first)
    doc.showPage()
    if second:
        doc.drawString(72, A4[1] - 72, second)
    doc.showPage()
    doc.save()
    return path


def test_text_pdf_never_calls_ocr() -> None:
    ocr = CountingOcr("x")
    pages = extract_pdf(FIX / "pdf/lesson-text.pdf", ocr)
    assert [p.page for p in pages] == list(range(1, n_pages(FIX / "pdf/lesson-text.pdf") + 1)) and ocr.calls == 0
    assert all(p.method == "pdf_text" for p in pages) and "l’école" in "".join(p.text for p in pages)


def test_scanned_pdf_ocrs_every_page_at_200_dpi() -> None:
    ocr = CountingOcr("Bonjour la classe")
    pages = extract_pdf(FIX / "pdf/lesson-scanned.pdf", ocr)
    assert ocr.calls == len(pages) == n_pages(FIX / "pdf/lesson-scanned.pdf")
    assert all(p.method == "pdf_ocr" for p in pages) and pages[0].text == "Bonjour la classe"
    assert abs(ocr.images[0].width - page_width_pt(FIX / "pdf/lesson-scanned.pdf") * 200 / 72) <= 1


def test_page_without_text_layer_uses_ocr(tmp_path: Path) -> None:
    pdf = two_page_pdf(tmp_path, "Bonjour, je m’appelle Ana et j’étudie le français.", "")  # pág. 2 vacía
    ocr = CountingOcr("Hola, me llamo Ana y estudio francés.")
    pages = extract_pdf(pdf, ocr)
    assert [p.method for p in pages] == ["pdf_text", "pdf_ocr"] and ocr.calls == 1
    assert "Bonjour" in pages[0].text and "Hola" in pages[1].text
