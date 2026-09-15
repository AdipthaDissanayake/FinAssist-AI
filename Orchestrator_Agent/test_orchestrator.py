"""Offline checks for the IR → Risk Agent coordination flow."""

from Orchestrator_Agent.O1 import orchestrate_financial_question


def fake_retrieval(query, *, top_k, engine):
    assert engine == "tavily"
    return {
        "query": query,
        "engine": "tavily-trusted-web-search",
        "evidence": [
            {
                "id": "ev-1",
                "text": "A variable loan rate may increase borrowing costs.",
                "source": "Test regulator",
                "url": "https://example.org/loan",
            }
        ],
    }


def fake_risk_analysis(query, evidence):
    assert evidence[0]["id"] == "ev-1"
    return {
        "summary": "A variable-rate loan can become more expensive.",
        "risks": [
            {
                "name": "Interest-rate risk",
                "level": "Medium",
                "level_reason": "The evidence describes a rate increase without a precise severity.",
                "explanation": "Borrowing costs may increase.",
                "evidence_ids": ["ev-1"],
            }
        ],
        "disclaimer": "Educational information only.",
        "sources": [{"id": "ev-1", "source": "Test regulator", "url": "https://example.org/loan"}],
        "grounded": True,
    }


def test_orchestrator_preserves_evidence_and_returns_trace():
    result = orchestrate_financial_question(
        "What are the risks of a variable-rate loan?", retrieve=fake_retrieval, analyse=fake_risk_analysis
    )
    assert result["risk_analysis"]["risks"][0]["evidence_ids"] == ["ev-1"]
    assert [step["agent"] for step in result["agent_trace"]] == ["information-retrieval", "risk-analysis"]
    assert "Interest-rate risk" in result["final_response"]
    assert "Level rationale" in result["final_response"]
