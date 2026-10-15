"""Tests del generador de fixtures sintéticos (Task FND-05).

Todo el contenido verificado aquí es sintético y sale de
``tests/fixtures/make_fixtures.py`` (Global Constraints: nunca datos reales).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from make_fixtures import generate  # noqa: E402

JSON_SUFFIXES = {".json", ".txt"}


def pdf_text(pdf_path: Path) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return "\n".join(page.get_textpage().get_text_range() for page in doc)
    finally:
        doc.close()


def _fraction_digits(update_time: str) -> int:
    """Número de decimales de un timestamp con sufijo Z u offset."""
    assert update_time.endswith(("Z", ":00"))
    core = update_time.split("T", 1)[1]
    core = core[:-1] if core.endswith("Z") else core[-8:]
    if "." in core:
        return len(core.split(".", 1)[1].rstrip("Z"))
    return 0


def _all_update_times(scenario_dir: Path) -> list[str]:
    out: list[str] = []
    for name, key in (
        ("courseWork.page1.json", "courseWork"),
        ("courseWork.page2.json", "courseWork"),
        ("courseWorkMaterials.json", "courseWorkMaterial"),
        ("announcements.json", "announcements"),
        ("topics.json", "topic"),
    ):
        payload = json.loads((scenario_dir / name).read_text(encoding="utf-8"))
        out.extend(item["updateTime"] for item in payload[key])
    return out


def test_fixtures_up_to_date(tmp_path: Path, fixtures_dir: Path) -> None:
    generate(tmp_path)
    generated = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert generated, "generate() no escribió ningún archivo"
    for p in generated:
        rel = p.relative_to(tmp_path)
        committed = fixtures_dir / rel
        assert committed.is_file(), f"falta commitear {rel}"
        if p.suffix in JSON_SUFFIXES:
            assert p.read_bytes() == committed.read_bytes(), f"difiere {rel}"
        elif p.suffix == ".pdf":
            assert pdf_text(p) == pdf_text(committed), f"difiere el texto de {rel}"
        elif p.suffix == ".png":
            assert p.read_bytes() == committed.read_bytes(), f"difiere {rel}"
        else:  # pragma: no cover
            raise AssertionError(f"sufijo inesperado: {rel}")


def test_scenario_shape(fixtures_dir: Path) -> None:
    scenario = fixtures_dir / "classroom" / "v1"
    courses = json.loads((scenario / "courses.json").read_text(encoding="utf-8"))["courses"]
    assert [(c["name"], c["courseState"]) for c in courses] == [
        ("Français A2 – Groupe 3", "ACTIVE"),
        ("Cálculo Diferencial", "ACTIVE"),
        ("Français A1 – 2025", "ARCHIVED"),
    ]
    topics = json.loads((scenario / "topics.json").read_text(encoding="utf-8"))["topic"]
    assert len(topics) == 3
    assert {t["courseId"] for t in topics} == {courses[0]["id"]}
    materials = json.loads((scenario / "courseWorkMaterials.json").read_text(encoding="utf-8"))
    assert len(materials["courseWorkMaterial"]) == 8
    announcements = json.loads((scenario / "announcements.json").read_text(encoding="utf-8"))
    assert len(announcements["announcements"]) == 6
    digits = {_fraction_digits(ts) for ts in _all_update_times(scenario)}
    assert {0, 3, 9} <= digits


def test_scanned_pdf_has_no_text_layer(fixtures_dir: Path) -> None:
    assert pdf_text(fixtures_dir / "pdf" / "lesson-scanned.pdf").strip() == ""
    assert "l’école" in pdf_text(fixtures_dir / "pdf" / "lesson-text.pdf")


def test_every_drive_file_is_attached(fixtures_dir: Path) -> None:
    from google_mock import FRENCH_COURSE_ID  # noqa: PLC0415

    drive_ids = {
        p.stem for p in (fixtures_dir / "drive" / "files").glob("*.json") if p.stem != "DIRMARKER"
    }
    assert drive_ids, "no hay metadatos en drive/files/"
    attached: set[str] = set()
    for scenario in ("v1", "v2", "deleted"):
        sdir = fixtures_dir / "classroom" / scenario
        payloads = [
            (json.loads((sdir / "courseWork.page1.json").read_text(encoding="utf-8")), "courseWork"),
            (json.loads((sdir / "courseWork.page2.json").read_text(encoding="utf-8")), "courseWork"),
            (
                json.loads((sdir / "courseWorkMaterials.json").read_text(encoding="utf-8")),
                "courseWorkMaterial",
            ),
            (json.loads((sdir / "announcements.json").read_text(encoding="utf-8")), "announcements"),
        ]
        for payload, key in payloads:
            for item in payload[key]:
                assert item["courseId"] == FRENCH_COURSE_ID, f"{item['id']} no es del curso francés"
                for mat in item.get("materials", []):
                    if "driveFile" in mat:
                        attached.add(mat["driveFile"]["driveFile"]["id"])
    assert drive_ids <= attached, f"archivos sin adjuntar: {sorted(drive_ids - attached)}"


def test_deleted_scenario_drops_one_material(fixtures_dir: Path) -> None:
    def ids(scenario: str) -> set[str]:
        payload = json.loads(
            (fixtures_dir / "classroom" / scenario / "courseWorkMaterials.json").read_text(
                encoding="utf-8"
            )
        )
        return {item["id"] for item in payload["courseWorkMaterial"]}

    assert len(ids("v1")) == 8
    assert len(ids("deleted")) == 7
    assert ids("deleted") < ids("v1")
