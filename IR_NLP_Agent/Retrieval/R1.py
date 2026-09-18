"""Explainable TF-IDF and optional Gemini-embedding retrieval engines."""

from __future__ import annotations

import math
import os
import re
import time
from collections import Counter
from typing import Any, Sequence
from urllib.parse import urlparse

from requests.exceptions import RequestException

try:
    from ..NLP.N1 import FinanceNLP
except ImportError:  # Supports running main.py directly from IR_NLP_Agent.
    from NLP.N1 import FinanceNLP


class TfidfRetriever:
    """Local lexical retrieval with transparent, reproducible relevance scores."""

    engine_name = "tfidf"

    def __init__(self, chunks: list[dict[str, Any]], nlp: FinanceNLP | None = None) -> None:
        if not chunks:
            raise ValueError("No knowledge-base chunks found. Add .pdf, .txt, or .md files to Data/Raw.")
        self.chunks = chunks
        self.nlp = nlp or FinanceNLP()
        self._idf = _calculate_idf([chunk["text"] for chunk in chunks], self.nlp)
        self.document_matrix = [_tfidf_vector(chunk["text"], self._idf, self.nlp) for chunk in chunks]

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        _validate_query(query, top_k)
        processed_query = self.nlp.preprocess_query(query) or query
        query_vector = _tfidf_vector(processed_query, self._idf, self.nlp)
        scores = [_sparse_cosine_similarity(query_vector, vector) for vector in self.document_matrix]
        return self._format_results(query, processed_query, scores, top_k)

    def _format_results(
        self, query: str, processed_query: str, scores: Sequence[float], top_k: int
    ) -> dict[str, Any]:
        ranked_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[:top_k]
        evidence: list[dict[str, Any]] = []
        for index in ranked_indices:
            if scores[index] <= 0:
                continue
            chunk = self.chunks[int(index)]
            evidence.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "score": round(scores[index], 4),
                    "source": chunk["source"],
                    "page": chunk["page"],
                    "entities": self.nlp.extract_entities(chunk["text"]),
                }
            )
        return {
            "query": query,
            "processed_query": processed_query,
            "query_entities": self.nlp.extract_entities(query),
            "engine": self.engine_name,
            "evidence": evidence,
            "message": None if evidence else "No relevant evidence was found in the local knowledge base.",
        }


class GeminiEmbeddingRetriever(TfidfRetriever):
    """Semantic retrieval using Gemini Embedding 2 and local cosine ranking.

    The documents remain visible in our own metadata and only their text is sent
    to Gemini to create embeddings. Do not index personal financial data or
    documents for which the team lacks permission.
    """

    engine_name = "gemini-embedding-2"

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        nlp: FinanceNLP | None = None,
        api_key: str | None = None,
        output_dimensionality: int = 768,
    ) -> None:
        if not chunks:
            raise ValueError("No knowledge-base chunks found. Add .pdf, .txt, or .md files to Data/Raw.")
        self.chunks = chunks
        self.nlp = nlp or FinanceNLP()
        self.output_dimensionality = output_dimensionality
        self._client, self._types = self._create_client(api_key)
        self.document_matrix = self._embed_documents()

    @staticmethod
    def _create_client(api_key: str | None) -> tuple[Any, Any]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini mode needs the google-genai package. Run: pip install google-genai"
            ) from exc

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Gemini mode needs GEMINI_API_KEY in your environment; do not hard-code it in source code.")
        return genai.Client(api_key=key), types

    def _embed_documents(self) -> list[list[float]]:
        contents = [
            self._types.Content(
                parts=[
                    self._types.Part.from_text(
                        text=f"title: {chunk['source']} | text: {chunk['text']}"
                    )
                ]
            )
            for chunk in self.chunks
        ]
        response = self._client.models.embed_content(
            model="gemini-embedding-2",
            contents=contents,
            config=self._types.EmbedContentConfig(output_dimensionality=self.output_dimensionality),
        )
        return [list(embedding.values) for embedding in response.embeddings]

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        _validate_query(query, top_k)
        processed_query = self.nlp.preprocess_query(query) or query
        response = self._client.models.embed_content(
            model="gemini-embedding-2",
            contents=f"task: search result | query: {processed_query}",
            config=self._types.EmbedContentConfig(output_dimensionality=self.output_dimensionality),
        )
        query_embedding = list(response.embeddings[0].values)
        scores = [_dense_cosine_similarity(query_embedding, document) for document in self.document_matrix]
        return self._format_results(query, processed_query, scores, top_k)


class GeminiGroundedRetriever:
    """Retrieve current, cited financial information with Gemini Google Search.

    This is the primary retrieval mode for FinAssist when no local knowledge
    base is required. It retrieves evidence and citations only; the Risk Agent
    is responsible for interpreting that evidence and producing the final
    financial-risk explanation.
    """

    engine_name = "gemini-google-search"

    def __init__(self, nlp: FinanceNLP | None = None, api_key: str | None = None) -> None:
        self.nlp = nlp or FinanceNLP()
        self._client = self._create_client(api_key)

    @staticmethod
    def _create_client(api_key: str | None) -> Any:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Gemini search mode needs the google-genai package. Run: pip install google-genai"
            ) from exc

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "Gemini search mode needs GEMINI_API_KEY in your environment; do not hard-code it in source code."
            )
        return genai.Client(api_key=key)

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        _validate_query(query, top_k)
        processed_query = self.nlp.preprocess_query(query) or query
        prompt = _grounded_retrieval_prompt(query, processed_query)
        interaction = self._client.interactions.create(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            input=prompt,
            tools=[{"type": "google_search"}],
        )
        answer_text, citations = _extract_grounded_output(interaction)
        evidence = _build_grounded_evidence(answer_text, citations, self.nlp, top_k)

        return {
            "query": query,
            "processed_query": processed_query,
            "query_entities": self.nlp.extract_entities(query),
            "engine": self.engine_name,
            "evidence": evidence,
            "message": (
                None
                if evidence
                else "Gemini returned no URL citations. Retry the query or ask for a more specific educational question."
            ),
        }


class AntigravityGroundedRetriever:
    """Retrieve web-grounded evidence with Gemini's Antigravity managed agent.

    Antigravity is a separate Gemini API agent with its own free-tier quota. It
    has Google Search enabled by default, so it is suitable when standard
    Gemini Google Search grounding is unavailable on the project's Free tier.
    """

    engine_name = "antigravity-google-search"

    def __init__(self, nlp: FinanceNLP | None = None, api_key: str | None = None) -> None:
        self.nlp = nlp or FinanceNLP()
        self._client = GeminiGroundedRetriever._create_client(api_key)

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        _validate_query(query, top_k)
        processed_query = self.nlp.preprocess_query(query) or query
        prompt = _grounded_retrieval_prompt(query, processed_query)
        max_total_tokens = _positive_integer_environment_value("ANTIGRAVITY_MAX_TOTAL_TOKENS", 16000)
        interaction = self._client.interactions.create(
            agent="antigravity-preview-05-2026",
            input=prompt,
            environment="remote",
            agent_config={"type": "antigravity", "max_total_tokens": max_total_tokens},
            tools=[
                {"type": "google_search"},
                {"type": "url_context"},
            ],
        )
        interaction = self._wait_for_interaction(interaction)
        answer_text, citations = _extract_grounded_output(interaction)
        if not citations:
            citations = _citations_from_explicit_urls(answer_text)
        evidence = _build_grounded_evidence(answer_text, citations, self.nlp, top_k)
        return {
            "query": query,
            "processed_query": processed_query,
            "query_entities": self.nlp.extract_entities(query),
            "engine": self.engine_name,
            "evidence": evidence,
            "retrieval_summary": answer_text,
            "agent_status": _interaction_status(interaction),
            "message": (
                None
                if evidence
                else _antigravity_empty_result_message(interaction, answer_text)
            ),
        }

    def _wait_for_interaction(self, interaction: Any) -> Any:
        """Poll a pending agent interaction for up to 90 seconds before parsing it."""
        deadline = time.monotonic() + 90
        while _interaction_status(interaction) == "in_progress" and time.monotonic() < deadline:
            time.sleep(3)
            interaction_id = _get_value(interaction, "id")
            if not interaction_id:
                break
            interaction = self._client.interactions.get(id=interaction_id)
        return interaction


class TavilyRetriever:
    """Retrieve finance evidence from approved websites using Tavily Search.

    Tavily performs retrieval only. This agent returns source snippets, URLs,
    relevance scores, and NLP metadata to the Orchestrator. The Risk Agent can
    then give that evidence to Gemini for grounded risk explanation.
    """

    engine_name = "tavily-trusted-web-search"

    def __init__(self, nlp: FinanceNLP | None = None, api_key: str | None = None) -> None:
        self.nlp = nlp or FinanceNLP()
        self._client = self._create_client(api_key)
        self.include_domains = _trusted_finance_domains()

    @staticmethod
    def _create_client(api_key: str | None) -> Any:
        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise RuntimeError(
                "Tavily mode needs the tavily-python package. Run: python -m pip install tavily-python"
            ) from exc

        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("Tavily mode needs TAVILY_API_KEY in your environment; do not hard-code it in source code.")
        client = TavilyClient(api_key=key)
        # Some local development environments set HTTP(S)_PROXY to a stale
        # loopback address. It makes all Tavily calls fail before they leave
        # the machine. Direct HTTPS is the safe local default; deployments
        # that deliberately use a managed proxy can opt back in explicitly.
        client.session.trust_env = _environment_flag("TAVILY_USE_SYSTEM_PROXY", default=False)
        return client

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        _validate_query(query, top_k)
        corrected_query, _ = self.nlp.correct_finance_spelling(query)
        processed_query = self.nlp.preprocess_query(corrected_query) or corrected_query
        try:
            response = self._client.search(
                query=_tavily_finance_query(corrected_query),
                search_depth=os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
                max_results=top_k,
                include_domains=self.include_domains,
                include_answer=False,
            )
        except RequestException as exc:
            raise RuntimeError(
                "Financial-source retrieval is temporarily unavailable. Check your internet connection or proxy settings, then try again."
            ) from exc
        evidence = []
        for result in response.get("results", [])[:top_k]:
            snippet = (result.get("content") or result.get("raw_content") or "").strip()
            evidence.append(
                {
                    "text": snippet,
                    "score": _optional_score(result.get("score")),
                    "source": result.get("title") or _source_name_from_url(result.get("url")),
                    "url": result.get("url"),
                    "page": None,
                    "entities": self.nlp.extract_entities(snippet),
                }
            )
        return {
            "query": query,
            "processed_query": processed_query,
            "query_entities": self.nlp.extract_entities(query),
            "engine": self.engine_name,
            "allowed_domains": self.include_domains,
            "evidence": evidence,
            "message": None if evidence else "No relevant evidence was found on the approved financial-source domains.",
        }


def _validate_query(query: str, top_k: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if len(query) > 1000:
        raise ValueError("query must not be longer than 1000 characters")
    if not isinstance(top_k, int) or not 1 <= top_k <= 10:
        raise ValueError("top_k must be an integer from 1 to 10")


def _environment_flag(name: str, default: bool = False) -> bool:
    """Read a simple boolean environment setting without accepting ambiguity."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z-]{1,}")


def _tokens(text: str, nlp: FinanceNLP) -> list[str]:
    """Create unigram and bigram terms for transparent local TF-IDF scoring."""
    normalised = nlp.preprocess_query(text)
    words = TOKEN_PATTERN.findall(normalised.lower())
    bigrams = [f"{words[index]} {words[index + 1]}" for index in range(len(words) - 1)]
    return words + bigrams


def _calculate_idf(texts: list[str], nlp: FinanceNLP) -> dict[str, float]:
    document_count = len(texts)
    frequencies: Counter[str] = Counter()
    for text in texts:
        frequencies.update(set(_tokens(text, nlp)))
    return {
        term: math.log((document_count + 1) / (frequency + 1)) + 1
        for term, frequency in frequencies.items()
    }


def _tfidf_vector(text: str, idf: dict[str, float], nlp: FinanceNLP) -> dict[str, float]:
    tokens = _tokens(text, nlp)
    if not tokens:
        return {}
    frequencies = Counter(tokens)
    total = len(tokens)
    return {term: (count / total) * idf[term] for term, count in frequencies.items() if term in idf}


def _sparse_cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot_product = sum(weight * right.get(term, 0.0) for term, weight in left.items())
    left_magnitude = math.sqrt(sum(weight * weight for weight in left.values()))
    right_magnitude = math.sqrt(sum(weight * weight for weight in right.values()))
    return dot_product / (left_magnitude * right_magnitude) if left_magnitude and right_magnitude else 0.0


def _dense_cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot_product = sum(a * b for a, b in zip(left, right))
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))
    return dot_product / (left_magnitude * right_magnitude) if left_magnitude and right_magnitude else 0.0


def _grounded_retrieval_prompt(query: str, processed_query: str) -> str:
    return f"""You are the FinAssist Information Retrieval Agent. Retrieve neutral, factual,
educational financial evidence for the question below. You are not the Risk Analysis Agent.

Requirements:
- You MUST use Google Search before answering. Open at least two relevant official sources with URL Context.
- Prioritise official central banks, financial regulators, stock exchanges, consumer-protection
  authorities, and regulated financial institutions. Avoid social-media posts and promotional sources.
- Provide only concise evidence relevant to the question. Do not give personalised advice, tell a
  user to buy or sell anything, make guarantees, or assign a final risk level.
- Include enough source-linked facts for another agent to analyse later.
- Finish with a `Sources:` section containing the complete `https://...` URL for each source used.

Original question: {query}
Processed finance terms: {processed_query}
"""


def _extract_grounded_output(interaction: Any) -> tuple[str, list[dict[str, Any]]]:
    """Extract Gemini's generated text and URL-citation annotations safely."""
    text_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    for step in _get_value(interaction, "steps", []) or []:
        if _get_value(step, "type") != "model_output":
            continue
        for content_block in _get_value(step, "content", []) or []:
            if _get_value(content_block, "type") != "text":
                continue
            content_text = _get_value(content_block, "text", "") or ""
            offset = len("".join(text_parts))
            text_parts.append(content_text)
            for annotation in _get_value(content_block, "annotations", []) or []:
                if _get_value(annotation, "type") != "url_citation":
                    continue
                citations.append(
                    {
                        "title": _get_value(annotation, "title", "Unknown source"),
                        "url": _get_value(annotation, "url"),
                        "start_index": _get_value(annotation, "start_index"),
                        "end_index": _get_value(annotation, "end_index"),
                        "offset": offset,
                    }
                )

    answer_text = "".join(text_parts).strip()
    if not answer_text:
        answer_text = (_get_value(interaction, "output_text", "") or "").strip()
    return answer_text, citations


def _build_grounded_evidence(
    answer_text: str, citations: list[dict[str, Any]], nlp: FinanceNLP, top_k: int
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for citation in citations:
        url = citation.get("url")
        if not url or url in seen_urls:
            continue
        start = citation.get("start_index")
        end = citation.get("end_index")
        if isinstance(start, int) and isinstance(end, int):
            start += citation["offset"]
            end += citation["offset"]
            excerpt = answer_text[start:end].strip()
        else:
            excerpt = answer_text
        evidence.append(
            {
                "text": excerpt or answer_text,
                "score": None,
                "source": citation.get("title") or "Unknown source",
                "url": url,
                "page": None,
                "entities": nlp.extract_entities(excerpt or answer_text),
            }
        )
        seen_urls.add(url)
        if len(evidence) == top_k:
            break
    return evidence


URL_PATTERN = re.compile(r'''https?://[^\s\]\[\)\}"'<>]+''', re.IGNORECASE)


def _citations_from_explicit_urls(answer_text: str) -> list[dict[str, Any]]:
    """Use source URLs written by Antigravity when annotation metadata is absent."""
    citations: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for match in URL_PATTERN.finditer(answer_text):
        url = match.group(0).rstrip(".,;:")
        if url in seen_urls:
            continue
        hostname = urlparse(url).netloc or "Source"
        citations.append(
            {
                "title": hostname,
                "url": url,
                "start_index": match.start(),
                "end_index": match.end(),
                "offset": 0,
            }
        )
        seen_urls.add(url)
    return citations


def _get_value(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


def _positive_integer_environment_value(variable_name: str, default: int) -> int:
    raw_value = os.getenv(variable_name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def _interaction_status(interaction: Any) -> str:
    status = _get_value(interaction, "status", "unknown")
    value = _get_value(status, "value", status)
    return str(value).lower()


def _antigravity_empty_result_message(interaction: Any, answer_text: str) -> str:
    status = _interaction_status(interaction)
    if status == "incomplete":
        return (
            "Antigravity did not finish within its token budget. Increase "
            "ANTIGRAVITY_MAX_TOTAL_TOKENS and retry."
        )
    if status == "in_progress":
        return "Antigravity is still processing the search. Retry the request in a moment."
    if answer_text:
        return "Antigravity returned text but no source URL. Retry with a more specific educational question."
    return f"Antigravity returned no final output (status: {status}). Retry the request."


DEFAULT_TRUSTED_FINANCE_DOMAINS = (
    "cbsl.gov.lk",
    "sec.gov.lk",
    "cse.lk",
    "consumerfinance.gov",
    "investor.gov",
    "federalreserve.gov",
    "imf.org",
    "worldbank.org",
)


def _trusted_finance_domains() -> list[str]:
    """Read an optional comma-separated source allow-list, otherwise use vetted defaults."""
    configured_domains = os.getenv("TAVILY_INCLUDE_DOMAINS", "")
    if configured_domains.strip():
        return [domain.strip().lower() for domain in configured_domains.split(",") if domain.strip()]
    return list(DEFAULT_TRUSTED_FINANCE_DOMAINS)


def _tavily_finance_query(query: str) -> str:
    """Format search query for financial risk and consumer protection retrieval.

    Avoid appending generic 'education' because it causes search engines to bias
    heavily toward student-education loans and ombudsman reports rather than
    general borrowing and consumer risks.
    """
    lowered = query.lower()
    if any(term in lowered for term in ("loan", "borrow", "debt", "mortgage", "credit")):
        return f"{query} borrowing risks repayment terms interest rate considerations"
    if any(term in lowered for term in ("invest", "stock", "share", "portfolio", "etf", "bond")):
        return f"{query} investment risks considerations volatility returns"
    if any(term in lowered for term in ("saving", "deposit", "fixed deposit", "emergency fund")):
        return f"{query} savings risks considerations interest rates liquidity"
    if any(term in lowered for term in ("budget", "income", "expense", "spending")):
        return f"{query} budgeting planning financial risks debt management"
    return f"{query} financial risks and considerations"


def _optional_score(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _source_name_from_url(url: Any) -> str:
    return urlparse(str(url)).netloc or "Unknown source"
