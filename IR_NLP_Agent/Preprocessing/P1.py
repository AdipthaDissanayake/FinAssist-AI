"""Cleaning, chunking, and JSON persistence for financial documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def clean_text(text: str) -> str:
    """Normalise whitespace while preserving the wording of source evidence."""
    text = text.replace("\u00ad", "")  # soft hyphen commonly found in PDFs
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_documents(
    pages: list[dict[str, Any]], chunk_size: int = 160, overlap: int = 30
) -> list[dict[str, Any]]:
    """Split page text into overlapping word chunks without losing provenance."""
    if chunk_size < 20:
        raise ValueError("chunk_size must be at least 20 words")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[dict[str, Any]] = []
    step = chunk_size - overlap
    for page in pages:
        words = clean_text(page["text"]).split()
        for start in range(0, len(words), step):
            segment = words[start : start + chunk_size]
            if not segment:
                continue
            chunk = {
                "chunk_id": f"{page['source']}::p{page['page']}::c{len(chunks) + 1}",
                "source": page["source"],
                "source_path": page["source_path"],
                "page": page["page"],
                "text": " ".join(segment),
            }
            chunks.append(chunk)
            if start + chunk_size >= len(words):
                break
    return chunks


def save_chunks(chunks: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")


def load_chunks(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
