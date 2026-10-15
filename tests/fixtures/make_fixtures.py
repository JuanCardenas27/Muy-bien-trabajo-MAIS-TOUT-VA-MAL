"""Generador determinista de fixtures sintéticos (Task FND-05).

Todo el contenido es inventado: ningún nombre, archivo o texto real del
Classroom (Global Constraints). Se usa así::

    python tests/fixtures/make_fixtures.py [OUT_DIR]

Sin argumentos escribe en el directorio ``tests/fixtures`` que contiene a
este script. La salida es idempotente: correr dos veces produce bytes
idénticos (los PDF usan ``invariant=1`` y Pillow no mete timestamps).
"""

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261014
BASE_TIME = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)

FRENCH_COURSE_ID = "cours_fr_a2_g3"

PDF_FILE_ID = "drive_pdf_lesson"
SLIDES_FILE_ID = "drive_slides_devoir"
LOCKED_FILE_ID = "drive_locked_doc"
DOC_FILE_ID = "drive_doc_texte"
IMAGE_FILE_ID = "drive_image_phrase"
MISSING_FILE_ID = "drive_missing_pdf"

DRIVE_FILE_IDS = (
    PDF_FILE_ID,
    SLIDES_FILE_ID,
    LOCKED_FILE_ID,
    DOC_FILE_ID,
    IMAGE_FILE_ID,
)

SCENARIOS = ("v1", "v2", "deleted")

FR_TITLES = [
    "Le passé composé",
    "Les articles définis",
    "La routine du matin",
    "Au marché",
    "Les adjectifs de couleur",
    "Le futur simple",
    "La météo de la semaine",
    "Les transports en ville",
    "À la cantine",
    "Le week-end en famille",
    "Les loisirs créatifs",
    "La maison et les pièces",
]

FR_SENTENCES = [
    "Les enfants chantent une chanson.",
    "Il fait beau en France.",
    "J’ai rendez-vous à onze heures.",
    "Le restaurant est très grand.",
    "Un bon vin blanc accompagne le repas.",
    "Nous allons au marché demain.",
    "Le chat dort près de la fenêtre.",
    "Marie lit un livre chaque soir.",
    "Ils jouent au ballon dans le jardin.",
    "La boulangerie ouvre à sept heures.",
    "Tu prends un café avec tes amis.",
    "Nous visitons le musée samedi.",
]

VOCAB_LINES = [
    "Vocabulaire — la rentrée (inventé)",
    "l’école — la escuela",
    "« Bonjour ! » — saludo con alegría",
    "Qu’est-ce que c’est ? — pregunta",
    "le cahier — el cuaderno",
    "la trousse — el estuche",
    "« Merci beaucoup ! » — agradecimiento",
    "l’ami fidèle — el amigo fiel",
    "le tableau noir — el tablero",
    "« À demain ! » — despedida",
    "la récréation — el recreo",
    "le stylo bleu — el bolígrafo azul",
    "« S’il vous plaît ? » — petición amable",
    "le devoir du jour — la tarea del día",
]

MIXED_LINES = [
    "Ficha mixta — español y francés (inventada)",
    "Hoy aprendemos: l’école y la maison.",
    "Repite en voz alta : « Bonjour ! »",
    "La frase del día: Les enfants chantent une chanson.",
    "Mañana practicamos le passé composé.",
    "Recuerda: « Merci beaucoup ! » siempre ayuda.",
    "Escucha y repite : Qu’est-ce que c’est ?",
    "Para la casa: escribe trois phrases nuevas.",
]

PHRASE_IMAGE_TEXT = "Les enfants chantent une chanson."


def _font_path() -> Path:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/fonts-dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError("no se encontró DejaVuSans.ttf (fonts-dejavu-core)")


def _fmt_ts(moment: datetime, digits: int, rng: random.Random) -> str:
    base = moment.strftime("%Y-%m-%dT%H:%M:%S")
    if digits == 0:
        return base + "Z"
    width = {3: 3, 9: 9}[digits]
    return f"{base}.{rng.randint(0, 10**width - 1):0{width}d}Z"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _drive_file_entry(file_id: str, title: str) -> dict[str, object]:
    return {"driveFile": {"driveFile": {"id": file_id, "title": title}, "shareMode": "VIEW"}}


def _build_classroom(rng: random.Random) -> dict[str, object]:
    courses = [
        {
            "id": FRENCH_COURSE_ID,
            "name": "Français A2 – Groupe 3",
            "section": "Groupe 3 (inventé)",
            "courseState": "ACTIVE",
            "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}",
            "creationTime": _fmt_ts(BASE_TIME - timedelta(days=30), 0, rng),
            "updateTime": _fmt_ts(BASE_TIME, 3, rng),
        },
        {
            "id": "cours_calc_1",
            "name": "Cálculo Diferencial",
            "section": None,
            "courseState": "ACTIVE",
            "alternateLink": "https://classroom.google.com/c/cours_calc_1",
            "creationTime": _fmt_ts(BASE_TIME - timedelta(days=40), 0, rng),
            "updateTime": _fmt_ts(BASE_TIME - timedelta(days=1), 9, rng),
        },
        {
            "id": "cours_fr_a1_2025",
            "name": "Français A1 – 2025",
            "section": None,
            "courseState": "ARCHIVED",
            "alternateLink": "https://classroom.google.com/c/cours_fr_a1_2025",
            "creationTime": _fmt_ts(BASE_TIME - timedelta(days=400), 0, rng),
            "updateTime": _fmt_ts(BASE_TIME - timedelta(days=200), 3, rng),
        },
    ]
    topics = [
        {
            "courseId": FRENCH_COURSE_ID,
            "topicId": topic_id,
            "name": name,
            "updateTime": _fmt_ts(BASE_TIME + timedelta(hours=i), i % 3 and 9 or 0, rng),
        }
        for i, (topic_id, name) in enumerate(
            [
                ("topic_vocabulaire", "Vocabulaire"),
                ("topic_grammaire", "Grammaire"),
                ("topic_comprehension", "Compréhension orale"),
            ]
        )
    ]

    coursework: list[dict[str, object]] = []
    for i in range(120):
        moment = BASE_TIME + timedelta(minutes=37 * i)
        digits = (0, 3, 9)[i % 3]
        title = f"{FR_TITLES[i % len(FR_TITLES)]} (exercice {i + 1:03d})"
        description = " ".join(rng.sample(FR_SENTENCES, k=2))
        materials: list[dict[str, object]] = []
        if i == 0:
            materials.append(_drive_file_entry(PDF_FILE_ID, "lesson-text.pdf"))
        elif i == 4:
            materials.append(_drive_file_entry(SLIDES_FILE_ID, "devoir-slides"))
        elif i == 9:
            materials.append(_drive_file_entry(DOC_FILE_ID, "texte-lecture"))
        elif i == 19:
            materials.append(_drive_file_entry(IMAGE_FILE_ID, "phrase.png"))
        elif i == 29:
            materials.append(_drive_file_entry(MISSING_FILE_ID, "ancien-devoir.pdf"))
        elif i % 17 == 0:
            materials.append(
                {
                    "link": {
                        "url": f"https://example.test/ressource-{i}",
                        "title": f"Ressource {i}",
                    }
                }
            )
        item: dict[str, object] = {
            "courseId": FRENCH_COURSE_ID,
            "id": f"cw_{i + 1:04d}",
            "title": title,
            "description": description,
            "materials": materials,
            "topicId": topics[i % len(topics)]["topicId"],
            "state": "PUBLISHED",
            "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}/a/cw_{i + 1:04d}",
            "creationTime": _fmt_ts(moment - timedelta(hours=2), 0, rng),
            "updateTime": _fmt_ts(moment, digits, rng),
        }
        if i % 5 == 0:
            item["dueDate"] = {"year": 2026, "month": 9, "day": 1 + (i % 27)}
        coursework.append(item)
    coursework.sort(key=lambda c: str(c["updateTime"]), reverse=False)

    material_defs = [
        ("m_0001", "Consignes générales (inventées)", [_drive_file_entry(PDF_FILE_ID, "lesson-text.pdf")]),
        ("m_0002", "Diaporama du devoir (inventé)", [_drive_file_entry(SLIDES_FILE_ID, "devoir-slides")]),
        ("m_0003", "Document verrouillé (inventé)", [_drive_file_entry(LOCKED_FILE_ID, "verrouille")]),
        ("m_0004", "Lecture du mardi (inventée)", [_drive_file_entry(DOC_FILE_ID, "texte-lecture")]),
        ("m_0005", "Image de la phrase (inventée)", [_drive_file_entry(IMAGE_FILE_ID, "phrase.png")]),
        ("m_0006", "Rappel sans pièce jointe (inventé)", []),
        ("m_0007", "Lien externe (inventé)", [{"link": {"url": "https://example.test/guide", "title": "Guide"}}]),
        ("m_0008", "Ancien polycopié (inventé)", [_drive_file_entry(PDF_FILE_ID, "lesson-text.pdf")]),
    ]
    materials_out: list[dict[str, object]] = []
    for i, (mid, title, mats) in enumerate(material_defs):
        moment = BASE_TIME + timedelta(hours=3 * i + 1)
        materials_out.append(
            {
                "courseId": FRENCH_COURSE_ID,
                "id": mid,
                "title": title,
                "description": rng.choice(FR_SENTENCES),
                "materials": mats,
                "topicId": topics[i % len(topics)]["topicId"],
                "state": "PUBLISHED",
                "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}/a/{mid}",
                "creationTime": _fmt_ts(moment - timedelta(hours=1), 0, rng),
                "updateTime": _fmt_ts(moment, (0, 3, 9)[i % 3], rng),
            }
        )

    announcements: list[dict[str, object]] = []
    for i in range(6):
        moment = BASE_TIME + timedelta(hours=5 * i + 2)
        mats = [_drive_file_entry(DOC_FILE_ID, "texte-lecture")] if i == 0 else []
        announcements.append(
            {
                "courseId": FRENCH_COURSE_ID,
                "id": f"a_{i + 1:04d}",
                "text": rng.choice(FR_SENTENCES),
                "materials": mats,
                "state": "PUBLISHED",
                "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}/a/a_{i + 1:04d}",
                "creationTime": _fmt_ts(moment - timedelta(minutes=30), 0, rng),
                "updateTime": _fmt_ts(moment, (9, 0, 3)[i % 3], rng),
            }
        )
    return {
        "courses": courses,
        "topics": topics,
        "coursework": coursework,
        "materials": materials_out,
        "announcements": announcements,
    }


def _write_scenario(out_dir: Path, name: str, data: dict[str, object]) -> list[Path]:
    sdir = out_dir / "classroom" / name
    coursework = [dict(item) for item in data["coursework"]]  # type: ignore[union-attr]
    coursework.sort(key=lambda c: str(c["updateTime"]), reverse=True)
    half = len(coursework) // 2
    page1 = {"courseWork": coursework[:half], "nextPageToken": "page2"}
    page2 = {"courseWork": coursework[half:]}
    materials = list(data["materials"])  # type: ignore[union-attr]
    if name == "deleted":
        materials = materials[:-1]
    return [
        _write_json(sdir / "courses.json", {"courses": data["courses"]}),
        _write_json(sdir / "topics.json", {"topic": data["topics"]}),
        _write_json(sdir / "courseWork.page1.json", page1),
        _write_json(sdir / "courseWork.page2.json", page2),
        _write_json(sdir / "courseWorkMaterials.json", {"courseWorkMaterial": materials}),
        _write_json(sdir / "announcements.json", {"announcements": data["announcements"]}),
    ]


def _build_drive(rng: random.Random, out_dir: Path, pdf_size: int, pdf_md5: str) -> list[Path]:
    ddir = out_dir / "drive"
    moment = BASE_TIME + timedelta(days=1)
    metas: list[tuple[str, dict[str, object]]] = [
        (
            PDF_FILE_ID,
            {
                "id": PDF_FILE_ID,
                "name": "lesson-text.pdf",
                "mimeType": "application/pdf",
                "version": "10",
                "size": str(pdf_size),
                "md5Checksum": pdf_md5,
                "capabilities": {"canDownload": True},
                "createdTime": _fmt_ts(moment, 0, rng),
                "modifiedTime": _fmt_ts(moment + timedelta(hours=2), 3, rng),
            },
        ),
        (
            SLIDES_FILE_ID,
            {
                "id": SLIDES_FILE_ID,
                "name": "devoir-slides",
                "mimeType": "application/vnd.google-apps.presentation",
                "version": "4",
                "capabilities": {"canDownload": True},
                "exportLinks": {
                    "text/plain": (
                        f"https://www.googleapis.com/drive/v3/files/{SLIDES_FILE_ID}"
                        "/export?mimeType=text/plain"
                    ),
                    "application/pdf": (
                        f"https://www.googleapis.com/drive/v3/files/{SLIDES_FILE_ID}"
                        "/export?mimeType=application/pdf"
                    ),
                },
                "createdTime": _fmt_ts(moment, 0, rng),
                "modifiedTime": _fmt_ts(moment + timedelta(hours=1), 9, rng),
            },
        ),
        (
            LOCKED_FILE_ID,
            {
                "id": LOCKED_FILE_ID,
                "name": "verrouille",
                "mimeType": "application/vnd.google-apps.document",
                "version": "2",
                "capabilities": {"canDownload": False},
                "exportLinks": {
                    "text/plain": (
                        f"https://www.googleapis.com/drive/v3/files/{LOCKED_FILE_ID}"
                        "/export?mimeType=text/plain"
                    ),
                },
                "createdTime": _fmt_ts(moment, 0, rng),
                "modifiedTime": _fmt_ts(moment, 0, rng),
            },
        ),
        (
            DOC_FILE_ID,
            {
                "id": DOC_FILE_ID,
                "name": "texte-lecture",
                "mimeType": "application/vnd.google-apps.document",
                "version": "6",
                "capabilities": {"canDownload": True},
                "exportLinks": {
                    "text/plain": (
                        f"https://www.googleapis.com/drive/v3/files/{DOC_FILE_ID}"
                        "/export?mimeType=text/plain"
                    ),
                },
                "createdTime": _fmt_ts(moment, 3, rng),
                "modifiedTime": _fmt_ts(moment + timedelta(hours=3), 3, rng),
            },
        ),
        (
            IMAGE_FILE_ID,
            {
                "id": IMAGE_FILE_ID,
                "name": "phrase.png",
                "mimeType": "image/png",
                "version": "3",
                "capabilities": {"canDownload": True},
                "createdTime": _fmt_ts(moment, 0, rng),
                "modifiedTime": _fmt_ts(moment, 9, rng),
            },
        ),
    ]
    written = [_write_json(ddir / "files" / f"{file_id}.json", meta) for file_id, meta in metas]
    slides_txt = (
        "Devoir — diaporama inventé\n"
        "Les enfants chantent une chanson.\n"
        "J’ai rendez-vous à onze heures.\n"
    )
    doc_txt = (
        "Lecture inventée\n"
        "Il fait beau en France.\n"
        "Nous allons au marché demain.\n"
        "Le restaurant est très grand.\n"
    )
    for file_id, text in ((SLIDES_FILE_ID, slides_txt), (DOC_FILE_ID, doc_txt)):
        target = ddir / "export" / f"{file_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    # MISSING_FILE_ID no tiene metadatos: el mock responde 404.
    return written


def _build_text_pdf(path: Path, lines: list[str]) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("DejaVu", str(_font_path())))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    doc.setTitle("Fixture inventé — français")
    doc.setAuthor("Frances Classroom (sintético)")
    width, height = A4
    text = doc.beginText(72, height - 72)
    text.setFont("DejaVu", 12)
    text.setLeading(20)
    for line in lines:
        text.textLine(line)
    doc.drawText(text)
    doc.showPage()
    doc.save()
    return path


def _build_scanned_pdf(source: Path, dest: Path) -> Path:
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    doc = pdfium.PdfDocument(str(source))
    try:
        out = canvas.Canvas(str(dest), invariant=1)
        out.setTitle("Fixture inventé — escaneado")
        out.setAuthor("Frances Classroom (sintético)")
        for page in doc:
            bitmap = page.render(scale=150 / 72)
            pil_image = bitmap.to_pil()
            width_pt = pil_image.size[0] * 72 / 150
            height_pt = pil_image.size[1] * 72 / 150
            out.setPageSize((width_pt, height_pt))
            out.drawImage(ImageReader(pil_image), 0, 0, width=width_pt, height=height_pt)
            out.showPage()
        out.save()
    finally:
        doc.close()
    return dest


def _build_phrase_image(path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(_font_path()), 32)
    canvas_size = (900, 120)
    image = Image.new("RGB", canvas_size, "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 40), PHRASE_IMAGE_TEXT, font=font, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path


def generate(out_dir: Path) -> list[Path]:
    """Genera todos los fixtures bajo ``out_dir`` y devuelve las rutas escritas."""
    rng = random.Random(SEED)
    written: list[Path] = []
    pdf_dir = out_dir / "pdf"
    text_pdf = _build_text_pdf(pdf_dir / "lesson-text.pdf", VOCAB_LINES)
    written.append(text_pdf)
    written.append(_build_text_pdf(pdf_dir / "lesson-text.v2.pdf", [*VOCAB_LINES, "Le renard brun saute."]))
    written.append(_build_text_pdf(pdf_dir / "mixed-es-fr.pdf", MIXED_LINES))
    written.append(_build_scanned_pdf(text_pdf, pdf_dir / "lesson-scanned.pdf"))
    written.append(_build_phrase_image(out_dir / "images" / "phrase.png"))

    pdf_bytes = text_pdf.read_bytes()
    data = _build_classroom(rng)
    for scenario in SCENARIOS:
        written.extend(_write_scenario(out_dir, scenario, data))
    # v2 usa la misma base pero el PDF fue reemplazado en Drive (Review Focus 2).
    written.extend(
        _build_drive(rng, out_dir, len(pdf_bytes), hashlib.md5(pdf_bytes).hexdigest())  # noqa: S324
    )
    return sorted(written)


def main(argv: list[str]) -> int:
    default = Path(__file__).resolve().parent
    out = Path(argv[1]) if len(argv) > 1 else default
    for path in generate(out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
