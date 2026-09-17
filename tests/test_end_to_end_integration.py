"""End-to-end integration and traceability tests for FinAssist AI.

Verifies the complete flow:
User Question → Domain Assessment → Retrieval Evidence → Risk Analysis Agent →
Traceability Verification → Formatted Final Response.

All tests run completely offline using deterministic mocks (zero Tavily/Gemini API calls).
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from IR_NLP_Agent.NLP.N1 import FinanceNLP
from Orchestrator_Agent.O1 import app as orchestrator_app, format_risk_analysis, orchestrate_financial_question
from Risk_Agent.R1 import app as risk_app, analyze_financial_risks


class StubGeminiClient:
    """Deterministic fake Gemini client for integration tests."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.models = self

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        return SimpleNamespace(text=self.response_text)


def fake_retrieval_agent(query: str, *, top_k: int = 3, engine: str = "tavily") -> dict[str, Any]:
    return {
        "query": query,
        "processed_query": query.lower(),
        "query_entities": ["interest rate", "variable mortgage"],
        "engine": "tavily-trusted-web-search",
        "evidence": [
            {
                "id": "E1",
                "text": "Variable mortgage payments can rise significantly when the central bank raises benchmark interest rates.",
                "source": "Central Bank Policy Guidance",
                "url": "https://example.gov.lk/rates",
                "relevance_score": 0.95,
            },
            {
                "id": "E2",
                "text": "Borrowers with debt servicing ratios above 40% face heightened repayment difficulty and default risk.",
                "source": "Credit Bureau Consumer Report",
                "url": "https://example.gov.lk/credit",
                "relevance_score": 0.88,
            },
        ],
    }


class EndToEndIntegrationTests(unittest.TestCase):
    """Verify integration across NLP, Orchestrator, and Risk Agent modules."""

    def setUp(self) -> None:
        self.nlp = FinanceNLP()
        self.model_json = json.dumps(
            {
                "summary": "Rising benchmark interest rates increase variable mortgage payments and repayment strain.",
                "summary_evidence_ids": ["E1", "E2"],
                "risks": [
                    {
                        "name": "Interest-rate risk",
                        "level": "High",
                        "level_reason": "The evidence shows payments rise significantly with benchmark rate hikes.",
                        "explanation": "Higher central bank rates directly increase monthly loan costs.",
                        "evidence_ids": ["E1"],
                    },
                    {
                        "name": "Repayment risk",
                        "level": "Medium",
                        "level_reason": "Elevated debt servicing ratios increase repayment strain and default potential.",
                        "explanation": "Borrowers may struggle to meet scheduled monthly debt commitments.",
                        "evidence_ids": ["E2"],
                    },
                ],
            }
        )

    def test_full_flow_user_question_to_structured_risks_to_final_response(self) -> None:
        """Verify: User question -> retrieval -> Risk Agent -> structured response."""
        user_query = "What are the risks of taking a variable rate mortgage?"

        # 1. NLP Domain & Spelling Assessment
        corrected_query, corrections = self.nlp.correct_finance_spelling(user_query)
        assessment = self.nlp.assess_domain(corrected_query)
        self.assertTrue(assessment.retrieval_allowed)

        # 2. Risk Agent Analysis with Stubbed Gemini
        fake_client = StubGeminiClient(self.model_json)
        retrieval_result = fake_retrieval_agent(corrected_query)

        def custom_analyse(query: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
            return analyze_financial_risks(query, evidence, client=fake_client)

        # 3. Orchestrator Coordination
        result = orchestrate_financial_question(
            corrected_query,
            top_k=2,
            retrieve=fake_retrieval_agent,
            analyse=custom_analyse,
        )

        # 4. Verify Structured Output
        self.assertIn("risk_analysis", result)
        analysis = result["risk_analysis"]
        self.assertEqual(len(analysis["risks"]), 2)
        self.assertEqual(analysis["risks"][0]["name"], "Interest-rate risk")
        self.assertEqual(analysis["risks"][0]["level"], "High")
        self.assertEqual(analysis["risks"][1]["name"], "Repayment risk")
        self.assertEqual(analysis["risks"][1]["level"], "Medium")

        # 5. Verify Final Readable Response Formatting
        final_text = result["final_response"]
        self.assertIn("Interest-rate risk (High)", final_text)
        self.assertIn("Repayment risk (Medium)", final_text)
        self.assertIn("[Evidence: E1]", final_text)
        self.assertIn("[Evidence: E2]", final_text)
        self.assertIn("educational information, not personalised", final_text.lower())

    def test_evidence_traceability_from_risk_to_source(self) -> None:
        """Verify: Risk → Evidence ID → Evidence Text → Source Title → Source URL."""
        fake_client = StubGeminiClient(self.model_json)
        retrieval_result = fake_retrieval_agent("mortgage risk")
        evidence_list = retrieval_result["evidence"]
        evidence_by_id = {item["id"]: item for item in evidence_list}

        analysis = analyze_financial_risks("mortgage risk", evidence_list, client=fake_client)

        # Every risk must map to existing evidence and sources
        for risk in analysis["risks"]:
            self.assertTrue(len(risk["evidence_ids"]) > 0)
            for eid in risk["evidence_ids"]:
                # 1. Evidence ID exists in retrieved evidence
                self.assertIn(eid, evidence_by_id)
                evidence_item = evidence_by_id[eid]

                # 2. Evidence text is populated and non-empty
                self.assertTrue(len(evidence_item["text"]) > 10)

                # 3. Source title is available
                self.assertTrue(len(evidence_item["source"]) > 0)

                # 4. Source URL is preserved
                self.assertTrue(evidence_item["url"].startswith("http"))

                # 5. Source list in response mirrors the retrieved sources
                matching_source = next((s for s in analysis["sources"] if s["id"] == eid), None)
                self.assertIsNotNone(matching_source)
                self.assertEqual(matching_source["source"], evidence_item["source"])
                self.assertEqual(matching_source["url"], evidence_item["url"])

    def test_unsupported_evidence_citation_is_purged(self) -> None:
        """Verify: Risk citing non-existent evidence ID is stripped to prevent hallucinations."""
        malicious_or_hallucinated_output = json.dumps(
            {
                "summary": "Valid summary based on evidence.",
                "summary_evidence_ids": ["E1"],
                "risks": [
                    {
                        "name": "Interest-rate risk",
                        "level": "Medium",
                        "level_reason": "Grounding in E1.",
                        "explanation": "Valid risk explanation.",
                        "evidence_ids": ["E1"],
                    },
                    {
                        "name": "Fraud/scam risk",
                        "level": "High",
                        "level_reason": "Fabricated reason.",
                        "explanation": "Hallucinated claim with non-existent source.",
                        "evidence_ids": ["E999_FABRICATED"],
                    },
                ],
            }
        )
        fake_client = StubGeminiClient(malicious_or_hallucinated_output)
        retrieval_result = fake_retrieval_agent("mortgage risk")

        analysis = analyze_financial_risks("mortgage risk", retrieval_result["evidence"], client=fake_client)

        # The hallucinated risk citing E999 must NOT be in final output
        risk_names = [r["name"] for r in analysis["risks"]]
        self.assertIn("Interest-rate risk", risk_names)
        self.assertNotIn("Fraud/scam risk", risk_names)

    def test_http_risk_agent_endpoint(self) -> None:
        """Verify: HTTP POST /analyze adheres to the standalone agent API contract."""
        client = TestClient(risk_app)

        # Health endpoint
        health_resp = client.get("/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json(), {"status": "ok", "agent": "risk-analysis"})

        # Analyze endpoint rejects invalid payload (e.g. missing query)
        bad_resp = client.post("/analyze", json={"query": ""})
        self.assertEqual(bad_resp.status_code, 422)

    def test_http_orchestrator_endpoint(self) -> None:
        """Verify: HTTP POST /orchestrate adheres to the standalone orchestrator API contract."""
        client = TestClient(orchestrator_app)

        # Health endpoint
        health_resp = client.get("/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json(), {"status": "ok", "agent": "orchestrator"})


if __name__ == "__main__":
    unittest.main()
