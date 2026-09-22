from pathlib import Path

from app.domain.models import IngestionErrorCode
from app.rag.ingestion.discovery import FileDiscovery


def test_discovery_is_deterministic_and_rejects_unsupported_and_oversized_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "notes.csv").write_text("a,b", encoding="utf-8")
    (tmp_path / "large.md").write_text("x" * 32, encoding="utf-8")

    discovery = FileDiscovery(tmp_path, max_file_size_bytes=16)
    first = discovery.discover()
    second = discovery.discover()

    assert [item.relative_path for item in first.files] == ["docs/guide.txt"]
    assert first.files == second.files
    assert first.files[0].document_id.startswith("doc-")
    assert first.files[0].document_version == f"sha256-{first.files[0].content_checksum}"
    assert {failure.code for failure in first.failures} == {
        IngestionErrorCode.UNSUPPORTED_DOCUMENT,
        IngestionErrorCode.INVALID_INPUT,
    }


def test_discovery_rejects_symlink_that_escapes_data_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "discovery-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "escaped.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        return

    result = FileDiscovery(tmp_path, max_file_size_bytes=128).discover()

    assert not result.files
    assert result.failures[0].code is IngestionErrorCode.INVALID_INPUT
    assert "escapes" in result.failures[0].message
