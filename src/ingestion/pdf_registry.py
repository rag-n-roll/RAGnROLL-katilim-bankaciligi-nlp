"""Kullanıcı PDF'lerini değişmez kaynak kayıtlarıyla doğrular."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
from pathlib import Path
import unicodedata
from typing import Any, Iterable


class PdfSourceIntegrityError(ValueError):
    """PDF adı veya içeriği kayıt defteriyle uyuşmadığında yükseltilir."""


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_filename(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


@dataclass(frozen=True)
class VerifiedPdfSource:
    document_id: str
    title: str
    sha256: str
    source_url: str
    publisher: str
    filename: str
    path: Path = field(repr=False)


class PdfSourceRegistry:
    def __init__(self, items: Iterable[dict[str, Any]]) -> None:
        self._by_filename: dict[str, dict[str, Any]] = {}
        for raw in items:
            item = dict(raw)
            required = {"document_id", "filenames", "sha256", "title", "source_url", "publisher"}
            missing = required.difference(item)
            if missing:
                raise PdfSourceIntegrityError(
                    "PDF kayıt alanları eksik: " + ", ".join(sorted(missing))
                )
            digest = str(item["sha256"]).casefold()
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise PdfSourceIntegrityError("PDF kayıt SHA-256 değeri geçersiz")
            filenames = item.get("filenames")
            if not isinstance(filenames, list) or not filenames:
                raise PdfSourceIntegrityError("PDF kayıt dosya adları geçersiz")
            for filename in filenames:
                key = _normalized_filename(str(filename))
                if key in self._by_filename:
                    raise PdfSourceIntegrityError(f"PDF dosya adı birden çok kayıtla eşleşiyor: {filename}")
                self._by_filename[key] = item

    @classmethod
    def from_items(cls, items: Iterable[dict[str, Any]]) -> "PdfSourceRegistry":
        return cls(items)

    @classmethod
    def from_path(cls, path: Path) -> "PdfSourceRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("documents") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise PdfSourceIntegrityError("PDF kayıt defteri liste içermelidir")
        return cls(items)

    def verify(self, path: Path) -> VerifiedPdfSource:
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            raise PdfSourceIntegrityError(f"PDF bulunamadı: {path.name}")
        item = self._by_filename.get(_normalized_filename(path.name))
        if item is None:
            raise PdfSourceIntegrityError(f"PDF dosya adı kayıtlı değil: {path.name}")
        actual = file_sha256(path)
        expected = str(item["sha256"]).casefold()
        if not hmac.compare_digest(actual, expected):
            raise PdfSourceIntegrityError(f"PDF kaynağı doğrulanamadı: {path.name}")
        return VerifiedPdfSource(
            document_id=str(item["document_id"]),
            title=str(item["title"]),
            sha256=expected,
            source_url=str(item["source_url"]),
            publisher=str(item["publisher"]),
            filename=path.name,
            path=path.resolve(),
        )

