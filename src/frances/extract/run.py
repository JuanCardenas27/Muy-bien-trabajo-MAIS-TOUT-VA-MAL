"""Etapa extract: texto etiquetado por idioma desde blobs (EXT-04)."""

import json
from pathlib import Path

import typer

from frances.cli import DataOpt, exit_with
from frances.db.usage import record_run
from frances.extract.lang import split_blocks
from frances.extract.ocr import ocr_file, ocr_image
from frances.extract.pdf import extract_pdf
from frances.extract.repo import ExtractCandidate, insert_extraction, list_extract_candidates
from frances.fetch.blobs import BlobStore
from frances.log import get_logger, redact
from frances.models import Extraction, ExtractMethod, Lang, TextBlock
from frances.stage import StageContext, StageReport, make_context
from frances.timeutil import format_ts

logger = get_logger(__name__)

EXTRACTOR_VERSION = "1"


def _read_text(path: Path) -> str:
    """UTF-8 tolerante: los bytes inválidos se sustituyen por U+FFFD."""
    return path.read_text(encoding="utf-8", errors="replace")


def _dispatch(cand: ExtractCandidate, path: Path) -> tuple[ExtractMethod, list[TextBlock]] | None:
    """Método y bloques según el mime; `None` si el mime no tiene soporte."""
    if cand.native:
        text = _read_text(path)
        return "export_text", split_blocks(text, cand.attachment_id)
    if cand.mime_type == "application/pdf":
        pages = extract_pdf(path, ocr=ocr_image)
        method: ExtractMethod = (
            "pdf_ocr" if any(page.method == "pdf_ocr" for page in pages) else "pdf_text"
        )
        blocks: list[TextBlock] = []
        for page in pages:
            blocks.extend(split_blocks(page.text, cand.attachment_id, page=page.page))
        return method, blocks
    if cand.mime_type.startswith("image/"):
        text = ocr_file(path)
        return "image_ocr", split_blocks(text, cand.attachment_id)
    if cand.mime_type.startswith("text/"):
        text = _read_text(path)
        return "plain", split_blocks(text, cand.attachment_id)
    return None


def _row_lang(blocks: list[TextBlock]) -> Lang:
    """Idioma con más caracteres entre los bloques; `unknown` si no hay bloques."""
    totals: dict[Lang, int] = {}
    for block in blocks:
        totals[block.lang] = totals.get(block.lang, 0) + len(block.text)
    if not totals:
        return "unknown"
    return max(totals, key=lambda lang: totals[lang])


def _process(ctx: StageContext, blobs: BlobStore, cand: ExtractCandidate, report: StageReport) -> None:
    dispatch = _dispatch(cand, blobs.path(cand.sha256))
    if dispatch is None:
        report.counts["extract.skipped_unsupported"] += 1
        return
    method, blocks = dispatch
    extraction = Extraction(
        blob_sha256=cand.sha256,
        extractor_version=EXTRACTOR_VERSION,
        method=method,
        blocks=blocks,
        char_count=sum(len(block.text) for block in blocks),
    )
    out_path = ctx.paths.extraction_path(cand.sha256, EXTRACTOR_VERSION)
    payload = json.dumps(extraction.model_dump(), sort_keys=True, indent=0, ensure_ascii=False)
    out_path.write_text(payload, encoding="utf-8")
    relative = str(out_path.relative_to(ctx.paths.root))
    with ctx.store.tx() as conn:
        insert_extraction(conn, extraction, _row_lang(blocks), relative, format_ts(ctx.now()))
    report.counts["extract.extracted"] += 1


def run_extract(ctx: StageContext) -> StageReport:
    """Extrae el texto de cada blob pendiente; idempotente por (blob, versión)."""
    report = StageReport(stage="extract", status="ok")
    report.counts = {
        "extract.extracted": 0,
        "extract.skipped_unsupported": 0,
        "extract.error": 0,
    }
    started_at = format_ts(ctx.now())
    blobs = BlobStore(ctx.paths)
    with ctx.store.tx() as conn:
        candidates = list_extract_candidates(conn, EXTRACTOR_VERSION)
    for cand in candidates:
        try:
            _process(ctx, blobs, cand, report)
        except Exception as exc:
            report.counts["extract.error"] += 1
            report.errors.append(f"{cand.sha256[:12]}: {type(exc).__name__}")
            logger.warning("extract %s: %s", cand.sha256[:12], redact(str(exc), ctx.env))
    if report.errors:
        report.status = "partial"
    with ctx.store.tx() as conn:
        record_run(conn, report, started_at, format_ts(ctx.now()))
    return report


def register(app: typer.Typer) -> None:
    """Registra `frances extract [--data DIR]` (R-05)."""

    @app.command()
    def extract(data: DataOpt = Path(".")) -> None:
        """Extrae texto etiquetado por idioma de los blobs descargados."""
        exit_with(lambda: run_extract(make_context(data)))
