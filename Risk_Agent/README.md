# FinAssist Financial Risk Analysis Agent — Mahee

This agent receives a financial question and source-linked evidence from the Information Retrieval Agent. Gemini explains only risks supported by that evidence; it does not search the web itself, predict markets, recommend products, or provide personalised financial advice.

```text
User → Orchestrator → IR/NLP Agent (Tavily) → retrieved evidence
     → Risk Analysis Agent (Gemini) → validation → Orchestrator → final response
```

The shared backend calls the Orchestrator in-process for a simple two-terminal demo. `POST /orchestrate` and `POST /analyze` remain available HTTP/JSON agent interfaces for independent deployment.

## Setup and run

From the project root:

```powershell
python -m pip install -r Risk_Agent/requirements.txt
```

Create a private root `.env` file. Never commit it:

```text
GEMINI_API_KEY=your-private-key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_USE_SYSTEM_PROXY=false
```

`GEMINI_API_KEY` is required for a real Gemini call. `GEMINI_MODEL` is optional because the agent defaults to `gemini-3.6-flash`. Direct HTTPS is the default so a stale local proxy does not block Gemini; set `GEMINI_USE_SYSTEM_PROXY=true` only for a deployment that intentionally uses its configured proxy.

Run a live demo:

```powershell
python Risk_Agent/R1.py --demo
```

Run the HTTP service:

```powershell
python -m uvicorn Risk_Agent.R1:app --reload --port 8001
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

## API contract

### `GET /health`

Returns:

```json
{"status":"ok","agent":"risk-analysis"}
```

### `POST /analyze`

The request is the actual IR-to-Risk contract. `page` is optional because web evidence has no page number while PDF/local evidence may have one.

```json
{
  "query": "What are the risks of a variable-rate loan?",
  "evidence": [
    {
      "id": "E1",
      "text": "A variable loan rate can increase borrowing costs when interest rates rise.",
      "source": "Central bank guidance",
      "url": "https://example.org/variable-rate-loans",
      "page": null,
      "score": 0.82,
      "entities": []
    }
  ]
}
```

The response keeps the original response fields and adds explainability fields only; the request contract and endpoint path are unchanged.

```json
{
  "summary": "Variable borrowing costs may increase.",
  "summary_evidence_ids": ["E1"],
  "risks": [
    {
      "name": "Interest-rate risk",
      "level": "Medium",
      "level_reason": "The evidence identifies rate changes but not exact severity.",
      "explanation": "Higher rates may raise borrowing costs.",
      "evidence_ids": ["E1"]
    }
  ],
  "disclaimer": "This is educational information, not personalised financial, investment, or lending advice...",
  "sources": [
    {"id":"E1","source":"Central bank guidance","url":"https://example.org/variable-rate-loans","page":null}
  ],
  "model": "gemini-3.6-flash",
  "grounded": true
}
```

Test the endpoint:

```powershell
$body = @{
  query = "What are the risks of a variable-rate loan?"
  evidence = @(@{
    id = "E1"
    text = "A variable loan rate can increase borrowing costs when interest rates rise."
    source = "Central bank guidance"
    url = "https://example.org/variable-rate-loans"
    page = $null
  })
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/analyze -ContentType 'application/json' -Body $body
```

## Agent-to-agent communication

1. The IR/NLP Agent returns `query`, `processed_query`, `query_entities`, `engine`, and an `evidence` list. Each evidence item has `text`, `source`, `url`, `page`, `score`, and NLP `entities`; an ID may be attached by the shared backend or assigned by the Risk Agent from its position.
2. The Orchestrator passes the same `evidence` list to `analyze_financial_risks(query, evidence)` without altering evidence text.
3. The Risk Agent returns the response above. The Orchestrator adds an `agent_trace` with retrieval and risk-analysis status, formats the readable response, and retains `risk_analysis` metadata for the frontend.

```text
User → Orchestrator → Information Retrieval Agent → Retrieved Evidence
→ Risk Analysis Agent → Gemini → Validation → Orchestrator → Final Response
```

## Risk Agent Architecture

The executable Mermaid diagrams use only components present in this repository:

- [Architecture pipeline](risk_agent_architecture.mmd)
- [Agent communication](agent_communication.mmd)
- [Risk-analysis sequence](risk_analysis_sequence.mmd)
- [Risk Agent data flow](risk_agent_data_flow.mmd)

The shared backend uses in-process Python calls: the Orchestrator calls the IR
function and then `analyze_financial_risks(query, evidence)`. The Risk Agent's
`POST /analyze` endpoint is also available for an independently deployed HTTP
agent service.

## Validation Pipeline

```text
Input → Pydantic input validation → grounded prompt → Gemini response
→ JSON/structure validation → risk category validation → risk level validation
→ evidence-ID validation → safety validation → validated structured output
```

Invalid or incomplete risk entries are removed. Invalid summaries, malformed
JSON, and unavailable model responses are rejected safely instead of being
shown as financial analysis.

## Grounding, validation, and Responsible AI

- Retrieved text is explicitly treated as untrusted data; instructions inside it are ignored.
- Gemini receives only supplied evidence and must use the predefined categories: interest-rate, repayment, credit, liquidity, market, concentration, inflation, and fraud/scam risk.
- Only `Low`, `Medium`, and `High` are accepted.
- The summary has `summary_evidence_ids`; every retained risk has valid `evidence_ids` and a grounded `level_reason`.
- Invalid risk categories, levels, incomplete risk records, and citations that do not exist in the evidence are removed. Missing or invalid summary citations are rejected as malformed model output.
- The response includes retrieved sources and an educational-not-advice disclaimer. Risk levels are not presented as an absolute decision.
- API keys are read from environment variables. The agent does not log keys or require account numbers, passwords, national IDs, or transaction data.

## Failure handling

- Empty question, empty evidence, or invalid evidence fields: FastAPI/Pydantic returns a clear `422` validation response.
- Gemini API failure: `502` with a safe service-unavailable message; no secret or provider traceback is returned to the client.
- Empty Gemini text, malformed JSON, missing summary, missing summary evidence IDs, or invalid response shape: safely rejected as a `502` rather than used.
- Insufficient evidence: a valid response may contain an empty `risks` list and a cited summary explaining that a conclusion cannot be supported.

## Evaluation and Testing

### Purpose

The evaluation checks whether the Risk Agent enforces its grounding and safety rules after an LLM response is received. It focuses on evidence-linked risk output, invalid-output rejection, prompt-injection resistance, disclaimers, and safe handling of insufficient evidence or service failures.

Run the deterministic offline suite from the project root:

```powershell
python Risk_Agent/evaluate_risk_agent.py
```

The smaller offline unit safety test can also be run with:

```powershell
python -c "from Risk_Agent.test_risk_agent import test_analysis_keeps_only_evidence_cited_risks; test_analysis_keeps_only_evidence_cited_risks()"
```

### Offline controlled validation

The 15-case evaluation suite uses **controlled/fake Gemini responses**. It therefore demonstrates the Risk Agent's validation, grounding, safety, and error-handling logic. It does **not** measure general real-world Gemini reasoning accuracy and must not be interpreted as a claim of 100% real-world accuracy.

Test categories and actual offline result:

| Category | Test cases | Actual result |
| --- | --- | --- |
| Normal financial risks | Variable-rate loan, missed repayment, concentration, liquidity, inflation, online scams | 6/6 passed |
| Insufficient evidence | Credit-risk question supported only by revenue-growth evidence | 1/1 passed; no risk invented |
| Invalid citations | Citation outside supplied evidence | 1/1 passed; invalid risk removed |
| Unsupported risk category | Risk category outside the approved taxonomy | 1/1 passed; risk removed |
| Invalid risk level | Level outside Low/Medium/High | 1/1 passed; risk removed |
| Prompt injection | Malicious instruction embedded in retrieved evidence | 1/1 passed; instruction treated as data and unsafe guarantee avoided |
| Failure handling | Malformed JSON, missing summary, missing summary citation, simulated Gemini failure | 4/4 passed; output safely rejected/handled |
| **Total** | **15 cases** | **15/15 passed** |

### Evaluation metrics

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Risk identification accuracy | 6/6 = 100% | All six controlled normal cases retained exactly the expected risk category. |
| Evidence citation validity | 18/18 = 100% | Every retained summary/risk citation existed in the supplied evidence. |
| Unsupported-claim rate after validation | 0/7 = 0% | No retained risk was outside its case's expected supported category. |
| Disclaimer presence | 11/11 = 100% | Every successful controlled response included the educational disclaimer. |
| Invalid-output rejection | 6/6 = 100% | Invalid citations, categories, levels, malformed/missing output, and simulated provider failure were safely handled. |
| Prompt-injection resistance | 1/1 = 100% | The controlled malicious evidence instruction was not followed. |

These metrics are calculated from the offline controlled cases only. They confirm that the implemented validation layer behaves as designed for this dataset.

### Real Gemini integration testing

**NOT RUN — Gemini free-tier quota exhausted.** No live Gemini API call was made for this evaluation run. Live testing must be repeated after quota access is available, using real Tavily evidence and representative user questions.

### Manual evaluation

The following cannot be measured reliably by controlled fake responses alone and require human review:

| Criterion | Manual review method |
| --- | --- |
| Evidence relevance | Check whether each retrieved Tavily snippet directly supports the generated risk. |
| Explanation usefulness | Ask two or more reviewers whether the explanation is understandable for a non-expert. |
| Risk-level appropriateness | Ask a finance lecturer or qualified reviewer whether the cautious risk level is reasonable. |

### Known Limitations

- Real Gemini evaluation is currently unavailable because the free-tier quota is exhausted.
- Offline tests cannot measure real LLM reasoning quality, hallucination frequency, or response consistency under varied live prompts.
- The current controlled evaluation dataset is relatively small (15 cases).
- More real-world evaluation with fresh retrieved evidence, repeated model runs, and human finance review is required before making any claim about general accuracy.
