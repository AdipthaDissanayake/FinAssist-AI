"""Financial Decision Support Agent for FinAssist AI.

The agent receives:
1. User financial question
2. Evidence-grounded Risk Analysis Agent output
3. Retrieved evidence

It uses Gemini to produce neutral decision-support considerations.

Important:
- It does NOT make financial decisions for the user.
- It does NOT tell the user to buy, sell, borrow, invest, or reject.
- If Gemini is unavailable, deterministic fallback logic is used.

Run:
    python -m uvicorn Decision_Support_Agent.D1:app --port 8003
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google import genai
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


app = FastAPI(
    title="FinAssist Financial Decision Support Agent",
    version="2.0.0",
)


# ---------------------------------------------------------
# Request model
# ---------------------------------------------------------

class DecisionSupportRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)

    risk_analysis: dict[str, Any]

    evidence: list[dict[str, Any]] = Field(
        default_factory=list
    )


# ---------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------

PROHIBITED_RECOMMENDATION_PATTERNS = [
    r"\byou should take\b",
    r"\byou should buy\b",
    r"\byou should sell\b",
    r"\byou should invest\b",
    r"\byou should borrow\b",
    r"\byou should reject\b",
    r"\bi recommend taking\b",
    r"\bi recommend buying\b",
    r"\bi recommend selling\b",
    r"\bbest option\b",
    r"\bguaranteed return\b",
]


def contains_direct_recommendation(text: str) -> bool:
    """Detect language that sounds like a financial decision."""

    normalized = text.lower()

    return any(
        re.search(pattern, normalized)
        for pattern in PROHIBITED_RECOMMENDATION_PATTERNS
    )


# ---------------------------------------------------------
# Evidence preparation
# ---------------------------------------------------------

def prepare_evidence(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only information needed by the Decision Support Agent."""

    prepared = []

    for index, item in enumerate(evidence, start=1):

        prepared.append(
            {
                "id": str(
                    item.get("id")
                    or item.get("chunk_id")
                    or index
                ),
                "text": item.get("text", ""),
                "source": item.get(
                    "source",
                    "Unknown source",
                ),
                "url": item.get("url"),
            }
        )

    return prepared


# ---------------------------------------------------------
# Gemini prompt
# ---------------------------------------------------------

def build_prompt(
    query: str,
    risk_analysis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> str:
    """Build the Decision Support Agent prompt."""

    return f"""
You are the Financial Decision Support Agent in FinAssist AI.

Your role is NOT to make financial decisions.

Your task is to convert evidence-grounded financial risks into
neutral things a user should consider before making their own
financial decision.

USER QUESTION:
{query}

RISK ANALYSIS:
{json.dumps(risk_analysis, ensure_ascii=False, indent=2)}

RETRIEVED EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

STRICT RULES:

1. Use the supplied risk analysis and evidence.
2. Do not invent unsupported financial facts.
3. Do not tell the user to take or reject a loan.
4. Do not tell the user to buy, sell, or choose an investment.
5. Do not decide whether something is good or bad for the user.
6. Do not provide personalised financial advice.
7. Use neutral language such as:
   - Consider...
   - Check...
   - Review...
   - Ask whether...
8. The user must remain the final decision maker.
9. Each consideration should relate to an identified risk.
10. Use evidence IDs when evidence supports the consideration.

Return ONLY valid JSON.

Use exactly this structure:

{{
  "summary": "short neutral explanation",
  "considerations": [
    {{
      "risk": "risk name",
      "level": "Low, Medium, High, or null",
      "things_to_consider": [
        "neutral consideration",
        "neutral consideration"
      ],
      "evidence_ids": ["1"]
    }}
  ],
  "questions_to_consider": [
    "question the user may ask before deciding"
  ],
  "disclaimer": "Educational decision-support information only. The user remains responsible for the final financial decision."
}}
"""


# ---------------------------------------------------------
# Gemini
# ---------------------------------------------------------

def call_gemini(
    query: str,
    risk_analysis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate decision-support information using Gemini."""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = build_prompt(
        query=query,
        risk_analysis=risk_analysis,
        evidence=evidence,
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    response_text = (
        response.text or ""
    ).strip()

    # Gemini may occasionally wrap JSON in markdown fences.
    if response_text.startswith("```"):
        response_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            response_text,
        )

        response_text = re.sub(
            r"\s*```$",
            "",
            response_text,
        )

    try:
        result = json.loads(
            response_text
        )

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON."
        ) from exc

    return result


# ---------------------------------------------------------
# Validate Gemini output
# ---------------------------------------------------------

def validate_decision_support(
    result: dict[str, Any],
) -> dict[str, Any]:
    """Validate structure and Responsible AI requirements."""

    considerations = result.get(
        "considerations"
    )

    if not isinstance(
        considerations,
        list,
    ):
        raise ValueError(
            "Decision-support considerations are missing."
        )

    questions = result.get(
        "questions_to_consider",
        [],
    )

    if not isinstance(
        questions,
        list,
    ):
        raise ValueError(
            "questions_to_consider must be a list."
        )

    # Check all generated text for direct financial recommendations.
    text_to_check = json.dumps(
        result,
        ensure_ascii=False,
    )

    if contains_direct_recommendation(
        text_to_check
    ):
        raise ValueError(
            "Decision Support Agent produced prohibited "
            "financial recommendation language."
        )

    # Always enforce our own disclaimer.
    result["disclaimer"] = (
        "This information is for educational decision support only. "
        "FinAssist does not make financial decisions for the user and "
        "does not provide personalised financial, investment, lending, "
        "legal, or gambling advice. The user remains responsible for "
        "the final decision."
    )

    result["generated_by"] = "gemini"

    return result


# ---------------------------------------------------------
# Fallback rule-based logic
# ---------------------------------------------------------

def fallback_considerations_for_risk(
    risk_name: str,
) -> list[str]:

    name = risk_name.lower()

    if (
        "repayment" in name
        or "affordability" in name
        or "debt" in name
    ):
        return [
            (
                "Compare the expected repayment with regular "
                "income and essential expenses."
            ),
            (
                "Consider whether repayments would remain "
                "manageable if income falls."
            ),
            (
                "Check the total repayment amount over the "
                "full borrowing period."
            ),
        ]

    if "interest" in name:
        return [
            "Check whether the interest rate is fixed or variable.",
            (
                "Consider how an increase in the interest rate "
                "could affect repayments."
            ),
            (
                "Review the total interest cost over the full "
                "agreement period."
            ),
        ]

    if "liquidity" in name:
        return [
            (
                "Check how easily the money can be accessed "
                "before maturity."
            ),
            "Review early-withdrawal restrictions or penalties.",
            (
                "Consider whether separate emergency funds "
                "are available."
            ),
        ]

    if "inflation" in name:
        return [
            (
                "Compare the expected return with possible "
                "inflation."
            ),
            (
                "Consider whether purchasing power could "
                "decrease over time."
            ),
        ]

    if (
        "concentration" in name
        or "diversification" in name
    ):
        return [
            (
                "Consider how much of the total portfolio is "
                "exposed to one investment."
            ),
            (
                "Review how a loss in one investment could "
                "affect the overall portfolio."
            ),
            (
                "Consider diversification when reviewing "
                "overall exposure."
            ),
        ]

    if (
        "fraud" in name
        or "scam" in name
    ):
        return [
            (
                "Verify that the financial provider is "
                "legitimate and appropriately regulated."
            ),
            (
                "Check official regulatory sources before "
                "providing money or sensitive information."
            ),
        ]

    if (
        "credit" in name
        or "default" in name
        or "counterparty" in name
        or "insolvency" in name
    ):
        return [
            "Assess the creditworthiness and financial health of the issuing institution or counterparty.",
            "Review whether default guarantees, deposit insurance, or collateral protections apply.",
            "Consider exposure limits to prevent heavy losses if an issuer defaults.",
        ]

    if (
        "market" in name
        or "volatility" in name
        or "price" in name
    ):
        return [
            "Evaluate your investment horizon against short-term price fluctuations and drawdowns.",
            "Determine your personal risk tolerance for potential capital drawdowns during market swings.",
            "Consider dollar-cost averaging or staggered entry rather than lump-sum timing.",
        ]

    if (
        "currency" in name
        or "exchange" in name
        or "forex" in name
        or "devaluation" in name
    ):
        return [
            "Analyze how foreign exchange rate shifts could reduce net yields or purchasing power.",
            "Review whether currency hedging strategies or local-currency alternatives are viable.",
            "Consider central bank foreign reserve and monetary policy trends impacting exchange rates.",
        ]

    if (
        "regulatory" in name
        or "policy" in name
        or "legal" in name
        or "tax" in name
    ):
        return [
            "Verify current regulatory compliance and tax obligations applicable to this instrument.",
            "Check for potential policy, capital control, or statutory amendments that may impact holding conditions.",
            "Consult qualified legal or tax advisory professionals for complex jurisdictional rules.",
        ]

    if (
        "operational" in name
        or "cyber" in name
        or "systemic" in name
    ):
        return [
            "Examine platform uptime, settlement safeguards, and operational infrastructure reliability.",
            "Review cybersecurity protocols, two-factor authentication, and account custody safety measures.",
            "Verify dispute resolution procedures in case of technical execution errors or disruptions.",
        ]

    if (
        "sovereign" in name
        or "country" in name
        or "geopolitical" in name
    ):
        return [
            "Assess the geopolitical stability, sovereign debt ratings, and economic outlook of the jurisdiction.",
            "Review capital repatriation rules and international transfer constraints.",
        ]

    return [
        f"Review the terms and conditions connected with {risk_name}.",
        f"Consider how {risk_name} could affect your overall financial situation.",
        "Check the relevant costs, restrictions, and supporting evidence before deciding.",
    ]


def build_fallback_result(
    query: str,
    risk_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Return safe decision support if Gemini is unavailable."""

    risks = (
        risk_analysis.get("risks")
        or []
    )

    considerations = []

    for risk in risks:

        risk_name = str(
            risk.get("name")
            or "Financial risk"
        )

        considerations.append(
            {
                "risk": risk_name,
                "level": risk.get("level"),
                "things_to_consider":
                    fallback_considerations_for_risk(
                        risk_name
                    ),
                "evidence_ids":
                    risk.get(
                        "evidence_ids",
                        [],
                    ),
            }
        )

    if not considerations:
        considerations.append(
            {
                "risk": (
                    "No specific supported risk identified"
                ),
                "level": None,
                "things_to_consider": [
                    (
                        "Review the financial product terms "
                        "and conditions."
                    ),
                    (
                        "Check costs, fees, access to funds, "
                        "and uncertainty."
                    ),
                    (
                        "Consider whether additional reliable "
                        "evidence is needed."
                    ),
                ],
                "evidence_ids": [],
            }
        )

    return {
        "query": query,
        "summary": (
            "These considerations are based on the "
            "evidence-grounded risks identified by the "
            "Risk Analysis Agent."
        ),
        "considerations": considerations,
        "questions_to_consider": [
            "What are the total costs and fees?",
            "What could increase the identified risks?",
            (
                "What terms and conditions should I verify "
                "before making my decision?"
            ),
        ],
        "disclaimer": (
            "This information is for educational decision "
            "support only. FinAssist does not make financial "
            "decisions for the user. The user remains "
            "responsible for the final decision."
        ),
        "generated_by": "rule-based-fallback",
    }


# ---------------------------------------------------------
# Main Decision Support function
# ---------------------------------------------------------

def generate_decision_support(
    query: str,
    risk_analysis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    First try Gemini.

    If Gemini fails or returns unsafe output,
    use deterministic fallback logic.
    """

    prepared_evidence = prepare_evidence(
        evidence
    )

    try:

        gemini_result = call_gemini(
            query=query,
            risk_analysis=risk_analysis,
            evidence=prepared_evidence,
        )

        validated_result = validate_decision_support(
            gemini_result
        )

        return validated_result

    except Exception:

        return build_fallback_result(
            query=query,
            risk_analysis=risk_analysis,
        )


# ---------------------------------------------------------
# API
# ---------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": "financial-decision-support",
        "llm": "gemini",
        "fallback": "enabled",
    }


@app.post("/support")
def support(
    request: DecisionSupportRequest,
) -> dict[str, Any]:

    try:

        return generate_decision_support(
            query=request.query,
            risk_analysis=request.risk_analysis,
            evidence=request.evidence,
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "The Financial Decision Support Agent "
                "encountered an unexpected error."
            ),
        ) from exc