# FinAssist Orchestrator Agent

This agent coordinates the required multi-agent workflow:

```text
Question → IR/NLP Agent (Tavily evidence) → Risk Agent (Gemini) → final response
```

The evidence list is passed unchanged to Mahee's Risk Agent. The response
includes `agent_trace`, `retrieval`, `risk_analysis`, and a readable
`final_response` so the team can demonstrate explainability in the viva.

## Run as a separate HTTP agent

```powershell
python -m uvicorn Orchestrator_Agent.O1:app --reload --port 8002
```

Then call it with JSON:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8002/orchestrate -ContentType 'application/json' -Body '{"query":"What are the risks of a variable-rate loan?","top_k":3}'
```

The shared backend also calls `orchestrate_financial_question()` directly so
the normal project demo needs only the backend and frontend terminals.
