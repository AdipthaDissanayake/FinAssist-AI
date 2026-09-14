# FinAssist-AI

Multi-agent AI system for financial information retrieval and risk analysis using LLMs, NLP, information retrieval, and security.

## Information Retrieval + NLP Agent

Adi's module is available in [`IR_NLP_Agent/README.md`](IR_NLP_Agent/README.md). It identifies finance entities, then uses Tavily to retrieve current source-linked evidence from trusted financial domains. Gemini is reserved for the Risk Agent's evidence-grounded reasoning. Local document retrieval remains an optional fallback.

## Run the shared chat interface

With the virtual environment activated, install the required packages and set the Tavily key privately:

```powershell
python -m pip install -r IR_NLP_Agent/requirements.txt
python -m pip install -r Backend/requirements.txt
python -m uvicorn Backend.B1:app --reload
```

The backend creates its required MySQL tables automatically when it starts; no manual table SQL is needed.

In another terminal, run the React frontend:

```powershell
cd Frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The shared UI stores chat history and IR evidence in MySQL. See [`Backend/README.md`](Backend/README.md) for MySQL setup, the integration contract, and required security work before deployment.
