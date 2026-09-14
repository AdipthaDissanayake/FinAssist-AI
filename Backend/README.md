# FinAssist Chat UI Backend

This development backend provides a shared ChatGPT-style UI, MySQL chat history, and a working integration point for Adi's Information Retrieval + NLP Agent.

## Run

From the project root, with the virtual environment activated, create the empty `finassist_ai` database in MySQL Workbench and add a private `DATABASE_URL` and `TAVILY_API_KEY` to `.env` (the root template is `.env.example`). The temporary existing `IR_NLP_Agent/.env` is also supported while the team moves to the root file.

```powershell
python -m pip install -r Backend/requirements.txt
python -m uvicorn Backend.B1:app --reload
```

The backend automatically creates all missing FinAssist tables during startup. You do not need to create tables manually in Workbench.

For the React UI during development, run `npm install` and `npm run dev` in `Frontend`, then open `http://localhost:5173`. After `npm run build`, FastAPI serves the React build at `http://127.0.0.1:8000`.

The backend loads `TAVILY_API_KEY` from `.env`. It uses `top_k=3` by default and saves source-backed IR results in dedicated retrieval tables.

## API contract

| Endpoint | Purpose | Team owner |
| --- | --- | --- |
| `POST /api/chats` | Create a conversation | Shared UI |
| `GET /api/chats` | Show conversation history | Shared UI |
| `GET /api/chats/{id}/messages` | Load one conversation | Shared UI |
| `POST /api/chats/{id}/messages` | Save question and retrieve evidence | Adi / Orchestrator integration |
| `GET /api/health` | Health check | Shaji / deployment |

`POST /api/chats/{id}/messages` sends the question to the IR + NLP Agent and stores the result in this MySQL structure:

```text
users → chats → messages → retrieval_runs → retrieval_evidence
```

The API dynamically returns source evidence under `assistant_message.metadata.retrieval` for the UI. Mahee's Risk Agent should read `retrieval.evidence`, call Gemini with that evidence, then write its final analysis in its own agent data/table.

Before Tavily is called, the backend runs an explainable finance-domain guard. Unrelated questions receive a transparent redirect and clickable finance suggestions without using an API call. Questions about financial risks of betting/gambling receive harm-awareness guidance, while requests for tips, odds, predictions, or strategies are declined.

## Security handoff for Taniya

This is a development scaffold only. It stores data in MySQL but has no authentication. Before production or any real user deployment, Taniya must add:

- Login/JWT identity and per-user chat ownership. The `users` table and `chats.user_id` foreign key already exist, but `user_id` stays `NULL` until verified JWT claims are available; never take an arbitrary `user_id` from the browser request.
- Authorization checks on every chat endpoint.
- Input sanitization and prompt-injection handling before the retrieval/LLM call.
- Consent, privacy notice, retention period, chat deletion, and secure production storage.
- Encryption, secrets management, rate limiting, audit logging, and safe error messages.

Do not use it to store real account numbers, passwords, national IDs, or sensitive financial records.
