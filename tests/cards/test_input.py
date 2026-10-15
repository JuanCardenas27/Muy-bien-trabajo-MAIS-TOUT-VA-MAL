"""Tests de ensamblado de GenerationInput por publicación (CRD-01)."""

from frances.cards.input import build_input, input_hash_for, items_needing_generation
from frances.db.store import Store
from frances.paths import DataPaths
from tests.cards.conftest import SEED_SHA, _add_extraction, _gen, _mark_deleted


def test_blocks_item_first_then_attachments_in_id_order(store: Store, paths: DataPaths) -> None:
    inp = build_input(store, paths, "mt_A")
    rest = [b.source for b in inp.blocks[1:]]
    assert inp.blocks[0].source == "item"
    assert inp.blocks[0].text.startswith("Leçon 1")
    assert rest == sorted(rest)


def test_input_hash_stable(store: Store, paths: DataPaths) -> None:
    h = build_input(store, paths, "mt_A").input_hash
    assert h == build_input(store, paths, "mt_A").input_hash == input_hash_for(store.conn, "mt_A")


def test_new_extraction_version_changes_hash(store: Store, paths: DataPaths) -> None:
    before = input_hash_for(store.conn, "mt_A")
    _add_extraction(store, paths, SEED_SHA, "2")
    assert input_hash_for(store.conn, "mt_A") != before


def test_removed_attachment_excluded(store: Store, paths: DataPaths) -> None:
    other = "f" * 64
    store.conn.execute(
        "INSERT INTO blobs (sha256, size, mime_type, created_at)"
        " VALUES (?, 19, 'text/plain', '2026-10-02T00:00:00Z')",
        (other,),
    )
    store.conn.execute(
        "INSERT INTO attachments (id, item_id, kind, external_id, title, blob_sha256, status,"
        " updated_at, removed_at) VALUES ('at_removed000001', 'mt_A', 'drive_file', 'file-2',"
        " 'Otro.txt', ?, 'downloaded', '2026-10-02T00:00:00Z', '2026-10-02T01:00:00Z')",
        (other,),
    )
    _add_extraction(store, paths, other, "1")
    inp = build_input(store, paths, "mt_A")
    assert all(b.source != f"sha256:{other}" for b in inp.blocks)
    assert [b.source for b in inp.blocks[1:]] == sorted(b.source for b in inp.blocks[1:])


def test_deleted_item_not_listed(store: Store) -> None:
    _mark_deleted(store, "mt_B")
    assert "mt_B" not in items_needing_generation(store, False, {"rules": "1", "llm": "1"})


def test_needs_generation_rules(store: Store) -> None:
    v = {"rules": "1", "llm": "1"}
    assert items_needing_generation(store, False, v) == ["mt_B", "mt_A"]
    _gen(store, "mt_A", input_hash_for(store.conn, "mt_A"), "rules", "1")
    assert "mt_A" not in items_needing_generation(store, False, v)
    assert "mt_A" in items_needing_generation(store, True, v)
    assert "mt_A" in items_needing_generation(store, False, {"rules": "2", "llm": "1"})
