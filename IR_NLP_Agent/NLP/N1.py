"""Small, explainable NLP layer for finance-focused information retrieval."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

try:
    from spacy.lang.en.stop_words import STOP_WORDS
except ImportError:  # The retrieval agent still has a clear error when spaCy is absent.
    STOP_WORDS = frozenset(
        {
            "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in",
            "into", "is", "it", "of", "on", "or", "the", "to", "what", "when", "where", "which",
            "with", "will", "would", "can", "could", "my", "your", "their", "this", "that",
        }
    )


FINANCE_TERMS: dict[str, tuple[str, ...]] = {
    "LOAN": ("loan", "borrowing", "borrower", "repayment", "installment", "credit"),
    "INTEREST_RATE": ("interest rate", "interest", "apr", "rate of return"),
    "INVESTMENT": ("investment", "invest", "portfolio", "share", "stock", "bond"),
    "SAVINGS": ("savings", "fixed deposit", "deposit", "emergency fund"),
    "RISK_TYPE": (
        "market risk",
        "credit risk",
        "liquidity risk",
        "concentration risk",
        "repayment risk",
        "interest-rate risk",
        "diversification",
    ),
}

MONEY_PATTERN = re.compile(r"(?:Rs\.?|LKR|USD|\$)\s?[\d,]+(?:\.\d+)?", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?%")
TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z-]{1,}")


class FinanceNLP:
    """Extract finance entities and normalise user questions for retrieval.

    It combines a transparent rule-based finance vocabulary with spaCy's named
    entities when the English model is installed. Rules ensure the module still
    works in a lightweight classroom setup.
    """

    def __init__(self) -> None:
        self._nlp = self._load_spacy_model()

    @staticmethod
    def _load_spacy_model() -> Any | None:
        try:
            import spacy

            try:
                return spacy.load("en_core_web_sm")
            except OSError:
                return spacy.blank("en")
        except ImportError:
            return None

    def preprocess_query(self, query: str) -> str:
        tokens = TOKEN_PATTERN.findall(query.lower())
        useful_tokens = [token for token in tokens if token not in STOP_WORDS]
        return " ".join(useful_tokens)

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        lowered = text.lower()
        entities: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(value: str, label: str) -> None:
            key = (value.lower(), label)
            if key not in seen:
                entities.append({"text": value, "label": label})
                seen.add(key)

        for label, terms in FINANCE_TERMS.items():
            for term in terms:
                if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered):
                    add(term, label)
        for value in MONEY_PATTERN.findall(text):
            add(value, "MONEY")
        for value in PERCENT_PATTERN.findall(text):
            add(value, "PERCENT")

        if self._nlp is not None:
            doc = self._nlp(text)
            for entity in doc.ents:
                if entity.label_ in {"ORG", "GPE", "DATE", "MONEY", "PERCENT"}:
                    add(entity.text, entity.label_)
        return entities

    def finance_labels(self, text: str) -> list[str]:
        return sorted({entity["label"] for entity in self.extract_entities(text)})

    def keyword_counts(self, text: str) -> dict[str, int]:
        tokens = TOKEN_PATTERN.findall(text.lower())
        return dict(Counter(token for token in tokens if token not in STOP_WORDS))
