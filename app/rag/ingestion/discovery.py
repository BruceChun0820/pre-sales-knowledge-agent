from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.domain.models import IngestionError, IngestionErrorCode

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".md", ".txt"})


@dataclass(frozen=True)
class DiscoveredFile:
    """A validated file inside the configured data root."""

    path: Path
    relative_path: str
    document_id: str
    document_version: str
    content_checksum: str
    size_bytes: int
    extension: str


@dataclass(frozen=True)
class DiscoveryResult:
    """Files eligible for parsing and typed failures for rejected candidates."""

    files: tuple[DiscoveredFile, ...]
    failures: tuple[IngestionError, ...]


class DiscoveryError(ValueError):
    """Raised when the configured data root cannot be inspected."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_id(relative_path: str) -> str:
    return f"doc-{hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:16]}"


class FileDiscovery:
    """Discover only supported, in-root regular files under an allowed root."""

    def __init__(
        self,
        root: Path,
        *,
        max_file_size_bytes: int,
        allowed_extensions: frozenset[str] = SUPPORTED_EXTENSIONS,
    ) -> None:
        if max_file_size_bytes < 1:
            raise ValueError("max_file_size_bytes must be positive")
        self.root = root.expanduser().resolve()
        self.max_file_size_bytes = max_file_size_bytes
        self.allowed_extensions = frozenset(extension.lower() for extension in allowed_extensions)

    def discover(self) -> DiscoveryResult:
        if not self.root.exists() or not self.root.is_dir():
            raise DiscoveryError(f"data root does not exist or is not a directory: {self.root}")

        files: list[DiscoveredFile] = []
        failures: list[IngestionError] = []
        for candidate in sorted(self.root.rglob("*"), key=lambda path: path.as_posix()):
            try:
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(self.root):
                    failures.append(
                        IngestionError(
                            code=IngestionErrorCode.INVALID_INPUT,
                            message="path escapes the configured data root",
                            source_uri=candidate.as_posix(),
                        )
                    )
                    continue
                if not resolved.is_file():
                    continue

                relative_path = resolved.relative_to(self.root).as_posix()
                extension = resolved.suffix.lower()
                if extension not in self.allowed_extensions:
                    failures.append(
                        IngestionError(
                            code=IngestionErrorCode.UNSUPPORTED_DOCUMENT,
                            message=f"unsupported file extension: {extension or '<none>'}",
                            source_uri=relative_path,
                        )
                    )
                    continue

                size_bytes = resolved.stat().st_size
                if size_bytes > self.max_file_size_bytes:
                    failures.append(
                        IngestionError(
                            code=IngestionErrorCode.INVALID_INPUT,
                            message=f"file exceeds the {self.max_file_size_bytes}-byte limit",
                            source_uri=relative_path,
                        )
                    )
                    continue

                checksum = _sha256(resolved)
                files.append(
                    DiscoveredFile(
                        path=resolved,
                        relative_path=relative_path,
                        document_id=_document_id(relative_path),
                        document_version=f"sha256-{checksum}",
                        content_checksum=checksum,
                        size_bytes=size_bytes,
                        extension=extension,
                    )
                )
            except OSError as exc:
                failures.append(
                    IngestionError(
                        code=IngestionErrorCode.UNKNOWN,
                        message=f"unable to inspect file: {exc}",
                        source_uri=candidate.as_posix(),
                    )
                )

        return DiscoveryResult(files=tuple(files), failures=tuple(failures))
