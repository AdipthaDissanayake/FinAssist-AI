"""Small, explainable NLP layer for finance-focused information retrieval."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import get_close_matches
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
    "LOAN": ("loan", "borrowing", "borrower", "repayment", "installment", "credit", "mortgage", "debt"),
    "INTEREST_RATE": ("interest rate", "interest", "apr", "rate of return"),
    "INVESTMENT": ("investment", "invest", "portfolio", "share", "stock", "bond", "crypto", "cryptocurrency"),
    "SAVINGS": ("savings", "fixed deposit", "deposit", "emergency fund", "saving"),
    "BUDGETING": ("budget", "budgeting", "income", "expense", "spending", "cash flow"),
    "FINANCIAL_PROTECTION": ("insurance", "fraud", "scam", "financial planning", "financial wellbeing"),
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

# Gambling information is handled separately from ordinary finance questions.
# We support harm-prevention questions but never betting tips, odds, picks, or
# strategies. This keeps the system aligned with its educational fintech scope.
BETTING_TERMS = ("betting", "bet", "gambling", "gamble", "casino", "wager", "sports betting", "lottery")
BETTING_RISK_TERMS = (
    "risk", "loss", "debt", "budget", "financial", "money", "harm", "addiction",
    "wellbeing", "well-being", "overspend", "spending", "affect", "problem gambling",
)
BETTING_ENABLEMENT_TERMS = ("tip", "tips", "odds", "predict", "prediction", "pick", "strategy", "strategies", "win")

# Frequent finance-domain misspellings are explicit so they can be explained
# and tested. Fuzzy matching below only applies to this small finance lexicon,
# never to arbitrary user words.
COMMON_FINANCE_MISSPELLINGS = {
    "bettng": "betting",
    "budjet": "budget",
    "crdit": "credit",
    "depoist": "deposit",
    "financil": "financial",
    "gambeling": "gambling",
    "insurence": "insurance",
    "interestrate": "interest rate",
    "interst": "interest",
    "intrest": "interest",
    "invesment": "investment",
    "investmant": "investment",
    "laon": "loan",
    "loen": "loan",
    "repaymant": "repayment",
    "savngs": "savings",
}

# Only distinctive finance terms may be fuzzy-matched. General words such as
# "risk", "rate", and "money" are intentionally excluded to avoid changing
# valid English wording (for example, "risks" must not become "risk").
FUZZY_FINANCE_TERMS = (
    "loan",
    "credit",
    "mortgage",
    "debt",
    "interest",
    "investment",
    "portfolio",
    "savings",
    "deposit",
    "budget",
    "insurance",
    "financial",
    "currency",
    "betting",
    "gambling",
)


@dataclass(frozen=True)
class DomainAssessment:
    """Transparent decision made before a web search or LLM call."""

    category: str
    retrieval_allowed: bool
    matched_terms: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

MONEY_PATTERN = re.compile(r"(?:\b(?:Rs\.?|LKR|USD)\s*|\$)\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
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

    def correct_finance_spelling(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """Correct likely finance typos while leaving normal language untouched.

        The user-facing message is not replaced. Callers store the original
        question and use this corrected version only for classification and
        retrieval. Each correction is returned for transparency.
        """

        corrections: list[dict[str, str]] = []
        corrected_parts: list[str] = []
        previous_end = 0
        vocabulary = FUZZY_FINANCE_TERMS

        for match in TOKEN_PATTERN.finditer(text):
            corrected_parts.append(text[previous_end:match.start()])
            original = match.group(0)
            lowered = original.lower()
            replacement = COMMON_FINANCE_MISSPELLINGS.get(lowered)
            if replacement is None and len(lowered) >= 4 and lowered not in vocabulary:
                close_matches = get_close_matches(lowered, vocabulary, n=1, cutoff=0.82)
                replacement = close_matches[0] if close_matches else None

            if replacement and replacement != lowered:
                replacement = replacement.capitalize() if original[0].isupper() else replacement
                corrected_parts.append(replacement)
                corrections.append({"from": original, "to": replacement})
            else:
                corrected_parts.append(original)
            previous_end = match.end()

        corrected_parts.append(text[previous_end:])
        return "".join(corrected_parts), corrections

    def assess_domain(self, text: str) -> DomainAssessment:
        """Decide whether a question should use financial web retrieval.

        The rule is intentionally conservative: a question must contain a
        finance signal, a monetary amount, or a finance entity. Gambling-risk
        education receives a safe redirect without external retrieval, while
        requests that could enable gambling are declined.
        """

        lowered = text.lower()
        betting_matches = self._matched_terms(lowered, BETTING_TERMS)
        if betting_matches:
            risk_matches = self._matched_terms(lowered, BETTING_RISK_TERMS)
            enablement_matches = self._matched_terms(lowered, BETTING_ENABLEMENT_TERMS)
            if risk_matches and not enablement_matches:
                return DomainAssessment(
                    category="gambling-risk",
                    retrieval_allowed=False,
                    matched_terms=sorted(set(betting_matches + risk_matches)),
                    reason="Supports financial-harm education without encouraging gambling.",
                )
            return DomainAssessment(
                category="restricted-gambling",
                retrieval_allowed=False,
                matched_terms=sorted(set(betting_matches + enablement_matches)),
                reason="Does not provide betting tips, predictions, odds, or strategies.",
            )

        finance_matches = self._matched_terms(
            lowered,
            tuple(term for terms in FINANCE_TERMS.values() for term in terms) + ("bank", "banking", "tax", "currency", "exchange rate", "financial"),
        )
        entities = self.extract_entities(text)
        finance_entity_labels = {label for label in FINANCE_TERMS if label in {item["label"] for item in entities}}
        has_monetary_value = bool(MONEY_PATTERN.search(text) or PERCENT_PATTERN.search(text))
        if finance_matches or finance_entity_labels or has_monetary_value:
            matched_terms = sorted(set(finance_matches + [entity["text"] for entity in entities if entity["label"] in finance_entity_labels]))
            if has_monetary_value:
                matched_terms.append("monetary-value")
            return DomainAssessment(
                category="finance",
                retrieval_allowed=True,
                matched_terms=matched_terms,
                reason="Matched transparent finance vocabulary or monetary information.",
            )

        return DomainAssessment(
            category="out-of-scope",
            retrieval_allowed=False,
            matched_terms=[],
            reason="No finance, monetary, or safe gambling-risk signal was found.",
        )

    @staticmethod
    def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
        return [term for term in terms if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text)]
