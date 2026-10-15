"""Generador determinista de fixtures sintéticos (Task FND-05).

Todo el contenido es inventado: nada real del Classroom. Uso:
``python tests/fixtures/make_fixtures.py [OUT_DIR]`` (idempotente).
"""

import hashlib
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20261014
BASE_TIME = datetime(2026, 8, 3, 13, 0, 0, tzinfo=UTC)

FRENCH_COURSE_ID = "cours_fr_a2_g3"

PDF_FILE_ID = "drive_pdf_lesson"
SLIDES_FILE_ID = "drive_slides_devoir"
LOCKED_FILE_ID = "drive_locked_doc"
DOC_FILE_ID = "drive_doc_texte"
IMAGE_FILE_ID = "drive_image_phrase"
MISSING_FILE_ID = "drive_missing_pdf"

DRIVE_FILE_IDS = (PDF_FILE_ID, SLIDES_FILE_ID, LOCKED_FILE_ID, DOC_FILE_ID, IMAGE_FILE_ID)
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
]

FR_SENTENCES = [
    "Les enfants chantent une chanson.",
    "Il fait beau en France.",
    "J’ai rendez-vous à onze heures.",  # noqa: RUF001
    "Le restaurant est très grand.",
    "Un bon vin blanc accompagne le repas.",
    "Nous allons au marché demain.",
    "Le chat dort près de la fenêtre.",
    "Marie lit un livre chaque soir.",
    "La boulangerie ouvre à sept heures.",
]

VOCAB_LINES = [
    "Vocabulaire — la rentrée (inventé)",
    "l’école — la escuela",  # noqa: RUF001
    "« Bonjour ! » — saludo con alegría",  # noqa: RUF001
    "Qu’est-ce que c’est ? — pregunta",  # noqa: RUF001
    "le cahier — el cuaderno",
    "la trousse — el estuche",
    "« Merci beaucoup ! » — agradecimiento",  # noqa: RUF001
    "l’ami fidèle — el amigo fiel",  # noqa: RUF001
    "le tableau noir — el tablero",
    "« À demain ! » — despedida",  # noqa: RUF001
    "la récréation — el recreo",
    "le stylo bleu — el bolígrafo azul",
    "« S’il vous plaît ? » — petición amable",  # noqa: RUF001
    "le devoir du jour — la tarea del día",
]

MIXED_LINES = [
    "Ficha mixta — español y francés (inventada)",
    "Hoy aprendemos: l’école y la maison.",  # noqa: RUF001
    "Repite en voz alta : « Bonjour ! »",  # noqa: RUF001
    "La frase del día: Les enfants chantent une chanson.",
    "Mañana practicamos le passé composé.",
    "Recuerda: « Merci beaucoup ! » siempre ayuda.",  # noqa: RUF001
    "Escucha y repite : Qu’est-ce que c’est ?",  # noqa: RUF001
]


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
    return f"{base}.{rng.randint(0, 10**digits - 1):0{digits}d}Z"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _drive_file_entry(file_id: str, title: str) -> dict[str, object]:
    return {"driveFile": {"driveFile": {"id": file_id, "title": title}, "shareMode": "VIEW"}}


def _course(cid: str, name: str, state: str, age: int, rng: random.Random) -> dict[str, object]:
    return {
        "id": cid,
        "name": name,
        "section": "Groupe 3 (inventé)" if cid == FRENCH_COURSE_ID else None,
        "courseState": state,
        "alternateLink": f"https://classroom.google.com/c/{cid}",
        "creationTime": _fmt_ts(BASE_TIME - timedelta(days=age), 0, rng),
        "updateTime": _fmt_ts(BASE_TIME, 3, rng),
    }


def _build_classroom(rng: random.Random) -> dict[str, object]:
    courses = [
        _course(FRENCH_COURSE_ID, "Français A2 – Groupe 3", "ACTIVE", 30, rng),  # noqa: RUF001
        _course("cours_calc_1", "Cálculo Diferencial", "ACTIVE", 40, rng),
        _course("cours_fr_a1_2025", "Français A1 – 2025", "ARCHIVED", 400, rng),  # noqa: RUF001
    ]
    topics = [
        {
            "courseId": FRENCH_COURSE_ID,
            "topicId": tid,
            "name": name,
            "updateTime": _fmt_ts(BASE_TIME + timedelta(hours=i), (0, 3, 9)[i % 3], rng),
        }
        for i, (tid, name) in enumerate(
            (
                ("topic_vocabulaire", "Vocabulaire"),
                ("topic_grammaire", "Grammaire"),
                ("topic_comprehension", "Compréhension orale"),
            )
        )
    ]
    # Cada archivo de drive/ queda adjunto a al menos una publicación (R-29).
    attach = {
        0: (PDF_FILE_ID, "lesson-text.pdf"),
        4: (SLIDES_FILE_ID, "devoir-slides"),
        9: (DOC_FILE_ID, "texte-lecture"),
        19: (IMAGE_FILE_ID, "phrase.png"),
        29: (MISSING_FILE_ID, "ancien-devoir.pdf"),
    }
    coursework: list[dict[str, object]] = []
    for i in range(120):
        moment = BASE_TIME + timedelta(minutes=37 * i)
        materials: list[dict[str, object]] = [_drive_file_entry(*attach[i])] if i in attach else []
        if i % 17 == 8:
            materials.append({"link": {"url": f"https://example.test/r{i}", "title": f"E{i}"}})
        item: dict[str, object] = {
            "courseId": FRENCH_COURSE_ID,
            "id": f"cw_{i + 1:04d}",
            "title": f"{FR_TITLES[i % len(FR_TITLES)]} (exercice {i + 1:03d})",
            "description": " ".join(rng.sample(FR_SENTENCES, k=2)),
            "materials": materials,
            "topicId": topics[i % len(topics)]["topicId"],
            "state": "PUBLISHED",
            "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}/a/cw_{i + 1:04d}",
            "creationTime": _fmt_ts(moment - timedelta(hours=2), 0, rng),
            "updateTime": _fmt_ts(moment, (0, 3, 9)[i % 3], rng),
        }
        if i % 5 == 0:
            item["dueDate"] = {"year": 2026, "month": 9, "day": 1 + (i % 27)}
        coursework.append(item)
    defs = [
        ("m_0001", "Consignes générales (inventées)", [(PDF_FILE_ID, "lesson-text.pdf")]),
        ("m_0002", "Diaporama du devoir (inventé)", [(SLIDES_FILE_ID, "devoir-slides")]),
        ("m_0003", "Document verrouillé (inventé)", [(LOCKED_FILE_ID, "verrouille")]),
        ("m_0004", "Lecture du mardi (inventée)", [(DOC_FILE_ID, "texte-lecture")]),
        ("m_0005", "Image de la phrase (inventée)", [(IMAGE_FILE_ID, "phrase.png")]),
        ("m_0006", "Rappel sin adjunto (inventé)", []),
        ("m_0007", "Lien externe (inventé)", []),
        ("m_0008", "Ancien polycopié (inventé)", [(PDF_FILE_ID, "lesson-text.pdf")]),
    ]

    def mat(i: int, mid: str, title: str, att: list[tuple[str, str]]) -> dict[str, object]:
        mats = [_drive_file_entry(*a) for a in att]
        if mid == "m_0007":
            mats = [{"link": {"url": "https://example.test/guide", "title": "Guide"}}]
        return _stream_item(
            mid,
            rng,
            BASE_TIME + timedelta(hours=3 * i + 1),
            (0, 3, 9)[i % 3],
            title=title,
            description=rng.choice(FR_SENTENCES),
            materials=mats,
            topicId=topics[i % len(topics)]["topicId"],
        )

    def ann(i: int) -> dict[str, object]:
        return _stream_item(
            f"a_{i + 1:04d}",
            rng,
            BASE_TIME + timedelta(hours=5 * i + 2),
            (9, 0, 3)[i % 3],
            text=rng.choice(FR_SENTENCES),
            materials=([_drive_file_entry(DOC_FILE_ID, "texte-lecture")] if i == 0 else []),
        )

    materials_out = [mat(i, mid, title, att) for i, (mid, title, att) in enumerate(defs)]
    announcements = [ann(i) for i in range(6)]
    return {
        "courses": courses,
        "topics": topics,
        "coursework": coursework,
        "materials": materials_out,
        "announcements": announcements,
    }


def _stream_item(
    iid: str, rng: random.Random, moment: datetime, digits: int, **extra: object
) -> dict[str, object]:
    return {
        "courseId": FRENCH_COURSE_ID,
        "id": iid,
        "state": "PUBLISHED",
        "alternateLink": f"https://classroom.google.com/c/{FRENCH_COURSE_ID}/a/{iid}",
        "creationTime": _fmt_ts(moment - timedelta(hours=1), 0, rng),
        "updateTime": _fmt_ts(moment, digits, rng),
        **extra,
    }


def _write_scenario(out_dir: Path, name: str, data: dict[str, object]) -> list[Path]:
    sdir = out_dir / "classroom" / name
    coursework = sorted(data["coursework"], key=lambda c: str(c["updateTime"]), reverse=True)  # type: ignore[union-attr]
    half = len(coursework) // 2
    materials = list(data["materials"])  # type: ignore[union-attr]
    materials = materials[:-1] if name == "deleted" else materials
    return [
        _write_json(sdir / "courses.json", {"courses": data["courses"]}),
        _write_json(sdir / "topics.json", {"topic": data["topics"]}),
        _write_json(
            sdir / "courseWork.page1.json",
            {"courseWork": coursework[:half], "nextPageToken": "page2"},
        ),
        _write_json(sdir / "courseWork.page2.json", {"courseWork": coursework[half:]}),
        _write_json(sdir / "courseWorkMaterials.json", {"courseWorkMaterial": materials}),
        _write_json(sdir / "announcements.json", {"announcements": data["announcements"]}),
    ]


def _export_links(file_id: str, *mimes: str) -> dict[str, str]:
    base = "https://www.googleapis.com/drive/v3"
    return {m: f"{base}/files/{file_id}/export?mimeType={m}" for m in mimes}


_MIME_SHORT = {
    "pdf": "application/pdf",
    "png": "image/png",
    "doc": "application/vnd.google-apps.document",
    "slides": "application/vnd.google-apps.presentation",
}
_EXPORT_SHORT = {"t": "text/plain", "p": "application/pdf"}

# (id, nombre, tipo, versión, horas_mod, dígitos_mod, descargable, exportaciones)
_DRIVE_SPECS = [
    (PDF_FILE_ID, "lesson-text.pdf", "pdf", "10", 2, 3, True, ()),
    (SLIDES_FILE_ID, "devoir-slides", "slides", "4", 1, 9, True, ("t", "p")),
    (LOCKED_FILE_ID, "verrouille", "doc", "2", 0, 0, False, ("t",)),
    (DOC_FILE_ID, "texte-lecture", "doc", "6", 3, 3, True, ("t",)),
    (IMAGE_FILE_ID, "phrase.png", "png", "3", 0, 9, True, ()),
]


def _build_drive(rng: random.Random, out_dir: Path, pdf_size: int, pdf_md5: str) -> list[Path]:
    ddir = out_dir / "drive"
    moment = BASE_TIME + timedelta(days=1)
    metas: list[tuple[str, dict[str, object]]] = []
    for fid, name, short, version, hours, digits, can_dl, exps in _DRIVE_SPECS:
        meta: dict[str, object] = {
            "id": fid,
            "name": name,
            "mimeType": _MIME_SHORT[short],
            "version": version,
            "capabilities": {"canDownload": can_dl},
            "createdTime": _fmt_ts(moment, 0, rng),
            "modifiedTime": _fmt_ts(moment + timedelta(hours=hours), digits, rng),
        }
        if exps:
            meta["exportLinks"] = _export_links(fid, *(_EXPORT_SHORT[e] for e in exps))
        metas.append((fid, meta))
    metas[0][1]["size"] = str(pdf_size)
    metas[0][1]["md5Checksum"] = pdf_md5
    written = [_write_json(ddir / "files" / f"{fid}.json", meta) for fid, meta in metas]
    exports = {
        SLIDES_FILE_ID: "Devoir — diaporama inventé\nLes enfants chantent une chanson.\n"
        "J’ai rendez-vous à onze heures.\n",  # noqa: RUF001
        DOC_FILE_ID: "Lecture inventée\nIl fait beau en France.\nNous allons au marché demain.\n"
        "Le restaurant est très grand.\n",
    }
    for fid, text in exports.items():
        target = ddir / "export" / f"{fid}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    # MISSING_FILE_ID no tiene metadatos: el mock responde 404.
    return written


def _build_text_pdf(path: Path, lines: list[str], title: str) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("DejaVu", str(_font_path())))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    doc.setTitle(title)
    doc.setAuthor("Frances Classroom (sintético)")
    text = doc.beginText(72, A4[1] - 72)
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
            pil_image = page.render(scale=150 / 72).to_pil()
            dims = (pil_image.size[0] * 72 / 150, pil_image.size[1] * 72 / 150)
            out.setPageSize(dims)
            out.drawImage(ImageReader(pil_image), 0, 0, width=dims[0], height=dims[1])
            out.showPage()
        out.save()
    finally:
        doc.close()
    return dest


def _build_phrase_image(path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(_font_path()), 32)
    image = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(image).text(
        (24, 40), "Les enfants chantent une chanson.", font=font, fill="black"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path


def generate(out_dir: Path) -> list[Path]:
    """Genera todos los fixtures bajo ``out_dir`` y devuelve las rutas escritas."""
    rng = random.Random(SEED)
    pdf_dir = out_dir / "pdf"
    title = "Fixture inventé — français"
    docs = [
        ("lesson-text.pdf", VOCAB_LINES),
        ("lesson-text.v2.pdf", [*VOCAB_LINES, "Le renard brun saute."]),
        ("mixed-es-fr.pdf", MIXED_LINES),
    ]
    text_pdf, v2_pdf, mixed_pdf = [
        _build_text_pdf(pdf_dir / name, lines, title) for name, lines in docs
    ]
    scanned_pdf = _build_scanned_pdf(text_pdf, pdf_dir / "lesson-scanned.pdf")
    phrase_png = _build_phrase_image(out_dir / "images" / "phrase.png")
    pdf_bytes = text_pdf.read_bytes()
    data = _build_classroom(rng)
    written = [text_pdf, v2_pdf, mixed_pdf, scanned_pdf, phrase_png]
    for scenario in SCENARIOS:
        written.extend(_write_scenario(out_dir, scenario, data))
    written.extend(_build_drive(rng, out_dir, len(pdf_bytes), hashlib.md5(pdf_bytes).hexdigest()))
    return sorted(written)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent
    print(*(str(p) for p in generate(out)), sep="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
