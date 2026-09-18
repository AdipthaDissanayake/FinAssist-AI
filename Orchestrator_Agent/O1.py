from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


IR_AGENT_URL = "http://127.0.0.1:8010"
RISK_AGENT_URL = "http://127.0.0.1:8001"
DECISION_SUPPORT_AGENT_URL = "http://127.0.0.1:8003"


class OrchestrationRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=5)


class AgentWorkflowError(RuntimeError):
    """Safe error used when another agent cannot be reached."""


def call_ir_agent(
    query: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """Send the user's query to the Information Retrieval Agent."""

    try:
        response = httpx.post(
            f"{IR_AGENT_URL}/retrieve",
            json={
                "query": query,
                "top_k": top_k,
                "engine": "tavily",
            },
            timeout=30.0,
        )

        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as exc:
        raise AgentWorkflowError(
            "The Information Retrieval Agent is temporarily unavailable."
        ) from exc


def normalize_evidence(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert evidence returned by the IR Agent into the format
    expected by the Risk Analysis Agent.
    """

    normalized_evidence = []

    for index, item in enumerate(evidence, start=1):
        evidence_id = (
            item.get("id")
            or item.get("chunk_id")
            or str(index)
        )

        normalized_evidence.append(
            {
                "id": evidence_id,
                "text": item.get("text", ""),
                "source": item.get(
                    "source",
                    "Unknown source",
                ),
                "url": item.get("url"),
                "page": item.get("page"),
                "score": item.get("score"),
                "entities": item.get(
                    "entities",
                    [],
                ),
            }
        )

    return normalized_evidence


def call_risk_agent(
    query: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send normalized evidence to the Risk Analysis Agent."""

    try:
        response = httpx.post(
            f"{RISK_AGENT_URL}/analyze",
            json={
                "query": query,
                "evidence": evidence,
            },
            timeout=60.0,
        )

        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as exc:
        raise AgentWorkflowError(
            "The Risk Analysis Agent is temporarily unavailable."
        ) from exc

    except httpx.RequestError as exc:
        raise AgentWorkflowError(
            "The Risk Analysis Agent is temporarily unavailable."
        ) from exc


def call_decision_support_agent(
    query: str,
    risk_analysis: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send the risk analysis to the Financial Decision Support Agent."""

    try:
        response = httpx.post(
            f"{DECISION_SUPPORT_AGENT_URL}/support",
            json={
                "query": query,
                "risk_analysis": risk_analysis,
                "evidence": evidence,
            },
            timeout=30.0,
        )

        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as exc:
        raise AgentWorkflowError(
            "The Financial Decision Support Agent is temporarily unavailable."
        ) from exc

    except httpx.RequestError as exc:
        raise AgentWorkflowError(
            "The Financial Decision Support Agent is temporarily unavailable."
        ) from exc


def format_risk_analysis(
    risk_analysis: dict[str, Any],
) -> str:
    """Convert structured risk JSON into a readable final response."""

    summary = risk_analysis.get(
        "summary",
        "Risk analysis completed.",
    )

    risks = risk_analysis.get(
        "risks",
        [],
    )

    lines = [summary]

    if risks:
        lines.append("\nRisks identified:")

        for risk in risks:
            name = risk.get(
                "name",
                "Risk",
            )

            level = risk.get(
                "level",
                "Unknown",
            )

            explanation = risk.get(
                "explanation",
                "",
            )

            lines.append(
                f"- {name} ({level}): {explanation}"
            )

    disclaimer = risk_analysis.get(
        "disclaimer"
    )

    if disclaimer:
        lines.append(
            f"\n{disclaimer}"
        )

    return "\n".join(lines)


def orchestrate_financial_question(
    query: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """
    Coordinate the complete flow:
    IR Agent -> Risk Agent -> Decision Support Agent -> Final response.
    """

    trace = []

    # -------------------------------------------------
    # Step 1 - Information Retrieval Agent
    # -------------------------------------------------

    retrieval = call_ir_agent(
        query=query,
        top_k=top_k,
    )

    evidence = (
        retrieval.get("evidence")
        or []
    )

    trace.append(
        {
            "agent": "information-retrieval",
            "status": "completed",
            "detail": (
                f"Retrieved {len(evidence)} "
                f"source item(s)."
            ),
        }
    )

    # -------------------------------------------------
    # Step 2 - Check whether evidence exists
    # -------------------------------------------------

    if not evidence:
        trace.append(
            {
                "agent": "risk-analysis",
                "status": "skipped",
                "detail": (
                    "No source evidence was available "
                    "for risk analysis."
                ),
            }
        )

        trace.append(
            {
                "agent": "financial-decision-support",
                "status": "skipped",
                "detail": (
                    "Decision support was skipped because "
                    "no grounded risk analysis was available."
                ),
            }
        )

        return {
            "query": query,
            "retrieval": retrieval,
            "risk_analysis": None,
            "decision_support": None,
            "agent_trace": trace,
            "final_response": (
                "I could not find enough trustworthy "
                "source evidence to perform a grounded "
                "risk analysis."
            ),
        }

    # -------------------------------------------------
    # Step 3 - Normalize evidence for Risk Agent
    # -------------------------------------------------

    normalized_evidence = normalize_evidence(
        evidence
    )

    trace.append(
        {
            "agent": "orchestrator",
            "status": "completed",
            "detail": (
                "Normalized retrieved evidence "
                "for the Risk Analysis Agent."
            ),
        }
    )

    # -------------------------------------------------
    # Step 4 - Risk Analysis Agent
    # -------------------------------------------------

    risk_analysis = call_risk_agent(
        query=query,
        evidence=normalized_evidence,
    )

    trace.append(
        {
            "agent": "risk-analysis",
            "status": "completed",
            "detail": (
                f"Generated "
                f"{len(risk_analysis.get('risks', []))} "
                f"risk item(s)."
            ),
        }
    )

    # -------------------------------------------------
    # Step 5 - Financial Decision Support Agent
    # -------------------------------------------------

    decision_support = call_decision_support_agent(
        query=query,
        risk_analysis=risk_analysis,
        evidence=normalized_evidence,
    )

    trace.append(
        {
            "agent": "financial-decision-support",
            "status": "completed",
            "detail": (
                "Generated neutral decision-support "
                "considerations and questions."
            ),
        }
    )

    # -------------------------------------------------
    # Step 6 - Final response
    # -------------------------------------------------

    final_response = format_risk_analysis(
        risk_analysis
    )

    return {
        "query": query,
        "retrieval": retrieval,
        "risk_analysis": risk_analysis,
        "decision_support": decision_support,
        "agent_trace": trace,
        "final_response": final_response,
    }


app = FastAPI(
    title="FinAssist Orchestrator Agent",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": "orchestrator",
    }


@app.post("/orchestrate")
def orchestrate(
    request: OrchestrationRequest,
) -> dict[str, Any]:

    try:
        return orchestrate_financial_question(
            query=request.query,
            top_k=request.top_k,
        )

    except AgentWorkflowError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The Orchestrator Agent encountered "
                "an unexpected error."
            ),
        ) from exc