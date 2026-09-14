"""Extract page-level text and source metadata from local knowledge-base files."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def extract_documents(data_directory: str | Path) -> list[dict[str, Any]]:
    """Read supported files and return one record per source page.

    Records retain the original filename and page number so every retrieved
    passage can be shown with a verifiable source in the UI.
    """
    root = Path(data_directory)
    if not root.exists():
        raise FileNotFoundError(f"Knowledge-base directory does not exist: {root}")

    pages: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.name.lower() == "readme.md":
            continue
        if path.suffix.lower() == ".pdf":
            pages.extend(_extract_pdf(path))
        else:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                pages.append(_page_record(path, page_number=1, text=text))
    return pages


def _extract_pdf(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to process PDF documents.") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf exposes several reader-specific errors
        raise ValueError(f"Could not read PDF '{path.name}': {exc}") from exc

    pages: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(_page_record(path, page_number, text))
    return pages


def _page_record(path: Path, page_number: int, text: str) -> dict[str, Any]:
    return {
        "source": path.name,
        "source_path": str(path),
        "page": page_number,
        "text": text,
    }
