"""FinAssist Information Retrieval + NLP Agent.

Use the primary Tavily web-retrieval mode:
    python IR_NLP_Agent/main.py --query "What are the risks of a loan?"

Use standard Gemini Google Search only with a paid Gemini API project:
    python IR_NLP_Agent/main.py --engine gemini-search --query "What are the risks of a loan?"

Use local, offline TF-IDF retrieval only when you have your own documents:
    python IR_NLP_Agent/main.py --engine local --query "How does diversification reduce risk?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .Extraction.E1 import extract_documents
    from .Preprocessing.P1 import chunk_documents, save_chunks
    from .Retrieval.R1 import (
        AntigravityGroundedRetriever,
        GeminiEmbeddingRetriever,
        GeminiGroundedRetriever,
        TavilyRetriever,
        TfidfRetriever,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from Extraction.E1 import extract_documents
    from Preprocessing.P1 import chunk_documents, save_chunks
    from Retrieval.R1 import (
        AntigravityGroundedRetriever,
        GeminiEmbeddingRetriever,
        GeminiGroundedRetriever,
        TavilyRetriever,
        TfidfRetriever,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIRECTORY = PROJECT_ROOT / "Data" / "Raw"
DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "Data" / "Processed" / "chunks.json"


def retrieve_financial_evidence(
    query: str,
    top_k: int = 5,
    engine: str = "tavily",
    data_directory: str | Path = DEFAULT_RAW_DIRECTORY,
) -> dict[str, Any]:
    """The public function Shaji's orchestrator can call or expose through HTTP."""
    if engine == "tavily":
        return TavilyRetriever().search(query=query, top_k=top_k)
    if engine == "antigravity":
        return AntigravityGroundedRetriever().search(query=query, top_k=top_k)
    if engine == "gemini-search":
        return GeminiGroundedRetriever().search(query=query, top_k=top_k)

    pages = extract_documents(data_directory)
    chunks = chunk_documents(pages)
    save_chunks(chunks, DEFAULT_CHUNKS_FILE)
    retriever = GeminiEmbeddingRetriever(chunks) if engine == "gemini-embeddings" else TfidfRetriever(chunks)
    return retriever.search(query=query, top_k=top_k)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve source-backed financial evidence.")
    parser.add_argument("--query", required=True, help="Financial question to search for.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of evidence chunks, from 1 to 10.")
    parser.add_argument(
        "--engine",
        choices=("tavily", "antigravity", "gemini-search", "local", "gemini-embeddings"),
        default="tavily",
        help="Tavily is the primary source-based web mode. Local modes require files in Data/Raw.",
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_RAW_DIRECTORY))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_arguments()
    try:
        result = retrieve_financial_evidence(
            query=arguments.query,
            top_k=arguments.top_k,
            engine=arguments.engine,
            data_directory=arguments.data_dir,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"Retrieval failed: {exc}") from exc
    print(json.dumps(result, indent=2, ensure_ascii=False))
