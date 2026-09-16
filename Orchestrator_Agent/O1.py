"""FinAssist Orchestrator Agent.

The Orchestrator owns the sequence between Adi's retrieval module and Mahee's
Risk Analysis Agent. It passes evidence through unchanged so every generated
risk can be traced back to the displayed source.

Run independently as an HTTP service:
    python -m uvicorn Orchestrator_Agent.O1:app --reload --port 8002
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from IR_NLP_Agent.main import retrieve_financial_evidence
from Risk_Agent.R1 import analyze_financial_risks


class OrchestrationRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=5)


class AgentWorkflowError(RuntimeError):
    """A safe error wrapper for an unavailable agent in the workflow."""


def orchestrate_financial_question(
    query: str,
    top_k: int = 3,
    *,
    retrieve: Callable[..., dict[str, Any]] = retrieve_financial_evidence,
    analyse: Callable[..., dict[str, Any]] = analyze_financial_risks,
) -> dict[str, Any]:
    """Retrieve financial evidence, then ask Mahee's agent to analyse it.

    Dependency injection makes the hand-off testable without network/API calls.
    The public FastAPI route below is the HTTP/JSON communication boundary that
    Shaji can deploy independently; the shared backend uses this function in
    process for a simple two-terminal development setup.
    """

    try:
        retrieval = retrieve(query, top_k=top_k, engine="tavily")
    except (RuntimeError, ValueError) as exc:
        raise AgentWorkflowError("The Information Retrieval Agent is temporarily unavailable.") from exc

    evidence = retrieval.get("evidence") or []
    trace: list[dict[str, str]] = [
        {"agent": "information-retrieval", "status": "completed", "detail": f"Retrieved {len(evidence)} source item(s)."}
    ]
    if not evidence:
        trace.append(
            {
                "agent": "risk-analysis",
                "status": "skipped",
                "detail": "No source evidence was available to analyse safely.",
            }
        )
        return {
            "query": query,
            "retrieval": retrieval,
            "risk_analysis": None,
            "agent_trace": trace,
            "final_response": (
                "I could not find enough trustworthy source evidence to provide a risk analysis. "
                "Please try a more specific financial question."
            ),
        }

    try:
        risk_analysis = analyse(query, evidence)
    except (RuntimeError, ValueError) as exc:
        raise AgentWorkflowError("The Risk Analysis Agent is temporarily unavailable.") from exc

    trace.append(
        {
            "agent": "risk-analysis",
            "status": "completed",
            "detail": f"Generated {len(risk_analysis.get('risks', []))} evidence-cited risk item(s).",
        }
    )
    return {
        "query": query,
        "retrieval": retrieval,
        "risk_analysis": risk_analysis,
        "agent_trace": trace,
        "final_response": format_risk_analysis(risk_analysis),
    }


def format_risk_analysis(analysis: dict[str, Any]) -> str:
    """Provide a readable final answer while retaining structured JSON metadata."""

    lines = [str(analysis.get("summary") or "I analysed the available financial evidence.")]
    risks = analysis.get("risks") or []
    if risks:
        lines.extend(["", "Possible risks:"])
        for risk in risks:
            cited_evidence = ", ".join(str(item) for item in risk.get("evidence_ids", []))
            level_reason = str(risk.get("level_reason") or "")
            lines.append(
                f"- {risk.get('name', 'Risk')} ({risk.get('level', 'Medium')}): "
                f"{risk.get('explanation', '')} [Evidence: {cited_evidence}]"
            )
            if level_reason:
                lines.append(f"  Level rationale: {level_reason}")
    else:
        lines.extend(["", "The available evidence was not sufficient to identify a supported risk category."])
    disclaimer = str(analysis.get("disclaimer") or "")
    if disclaimer:
        lines.extend(["", disclaimer])
    return "\n".join(lines)


app = FastAPI(title="FinAssist Orchestrator Agent", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "orchestrator"}


@app.post("/orchestrate")
def orchestrate(request: OrchestrationRequest) -> dict[str, Any]:
    """HTTP/JSON orchestration endpoint for an independently deployed flow."""

    try:
        return orchestrate_financial_question(request.query, request.top_k)
    except AgentWorkflowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
