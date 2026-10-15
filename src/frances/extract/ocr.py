"""OCR de imágenes en francés y español con Tesseract (``fra+spa``)."""

from pathlib import Path

import pytesseract  # type: ignore[import-untyped]
from PIL import Image, ImageOps


def preprocess(img: Image.Image) -> Image.Image:
    """Escala de grises + autocontraste; duplica si el ancho es menor de 1000 px."""
    gray = ImageOps.autocontrast(ImageOps.grayscale(img))
    width, height = gray.size
    if width < 1000:
        return gray.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    return gray


def ocr_image(img: Image.Image, langs: str = "fra+spa") -> str:
    """Texto de una imagen ya abierta con :func:`preprocess` aplicado."""
    return str(pytesseract.image_to_string(preprocess(img), lang=langs, config="--psm 6"))


def ocr_file(path: Path) -> str:
    """Texto de un archivo de imagen en disco."""
    with Image.open(path) as img:
        img.load()
        return ocr_image(img)


def tesseract_version() -> str:
    """Versión del binario ``tesseract`` como texto."""
    return str(pytesseract.get_tesseract_version())
