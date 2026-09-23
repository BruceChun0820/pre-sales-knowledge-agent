from pathlib import Path

from app.rag.ingestion.discovery import FileDiscovery
from app.rag.ingestion.manifest import ManifestStatus, ManifestStore, update_manifest_entry


def test_manifest_store_round_trips_sorted_jsonl_entries(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    files = FileDiscovery(tmp_path, max_file_size_bytes=128).discover().files
    store = ManifestStore(tmp_path / "manifest.jsonl")

    store.upsert(store_entry(files[1]))
    store.upsert(store_entry(files[0]))

    loaded = store.load()
    assert [entry.source_uri for entry in loaded] == ["a.txt", "b.txt"]
    assert len((tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    parsed = update_manifest_entry(
        loaded[0], status=ManifestStatus.PARSED, parser_name="text", parser_version="text-v1"
    )
    store.upsert(parsed)
    assert store.get(parsed.document_id).status is ManifestStatus.PARSED
    assert store.get(parsed.document_id).parser_name == "text"


def store_entry(discovered):
    from app.rag.ingestion.manifest import ManifestEntry

    return ManifestEntry.from_discovered_file(discovered)
