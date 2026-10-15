"""Normalización de adjuntos materials → Attachment (SYN-05, TDD rojo)."""

import logging

import pytest

from frances.models.ids import attachment_id
from frances.sync.attachments import extract_attachments

LINK_A = {"link": {"url": "https://example.org/conjugaison", "title": "Conjugaison"}}
DRIVE_X = {
    "driveFile": {
        "driveFile": {
            "id": "f_x",
            "title": "Leçon X",
            "alternateLink": "https://drive.google.com/f_x",
        }
    }
}


def test_each_material_kind() -> None:
    raw = {
        "materials": [
            {
                "driveFile": {
                    "driveFile": {
                        "id": "f_pdf",
                        "title": "Leçon 1",
                        "alternateLink": "https://drive.google.com/f_pdf",
                    }
                }
            },
            {
                "youtubeVideo": {
                    "id": "yt_abc",
                    "title": "Vidéo",
                    "alternateLink": "https://youtu.be/yt_abc",
                }
            },
            {"link": {"url": "https://example.org/conjugaison", "title": "Conjugaison"}},
            {
                "form": {
                    "formUrl": "https://docs.google.com/forms/d/e/FORM1/viewform",
                    "title": "Quiz",
                }
            },
        ]
    }
    atts = extract_attachments(raw, "cw_1002")
    assert [(a.kind, a.external_id) for a in atts] == [
        ("drive_file", "f_pdf"),
        ("youtube", "yt_abc"),
        ("link", "https://example.org/conjugaison"),
        ("form", "https://docs.google.com/forms/d/e/FORM1/viewform"),
    ]
    assert atts[0].id == attachment_id("cw_1002", "drive_file", "f_pdf")
    assert atts[0].url == "https://drive.google.com/f_pdf" and atts[0].title == "Leçon 1"
    assert all(a.mime_type is None for a in atts)


def test_dedupes_by_kind_and_external_id_keeping_order() -> None:
    raw = {"materials": [LINK_A, DRIVE_X, LINK_A]}
    atts = extract_attachments(raw, "cw_1002")
    assert [a.external_id for a in atts] == ["https://example.org/conjugaison", "f_x"]
    assert [a.kind for a in atts] == ["link", "drive_file"]


def test_unknown_material_ignored_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    raw = {"materials": [{"hologram": {"secret": "VALOR-SECRETO-XYZ"}}]}
    with caplog.at_level(logging.WARNING, logger="frances.sync.attachments"):
        atts = extract_attachments(raw, "cw_1002")
    assert atts == []
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "se esperaba un registro WARNING"
    assert any("hologram" in r.getMessage() for r in warnings)
    assert all("VALOR-SECRETO-XYZ" not in r.getMessage() for r in warnings)


def test_no_materials_returns_empty() -> None:
    assert extract_attachments({}, "cw_1002") == []
