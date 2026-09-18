# FinAssist AI — Information Retrieval and NLP Implementation Summary

**Contributor:** Adi  
**Module:** Information Retrieval (IR), Natural Language Processing (NLP), shared chat UI, and chat-history backend  
**Project:** FinAssist AI — Agentic Fintech Research System

## 1. Contribution overview

This work implements the Information Retrieval and NLP layer of FinAssist AI. The module accepts a user's financial question, checks that it is within the system's financial-education scope, identifies finance-related entities, retrieves current evidence from trusted web sources, and stores the question and retrieved evidence for later use by the other agents.

The shared React interface and FastAPI/MySQL backend were also created to make the IR module easy for the team to integrate and demonstrate.

## 2. Implemented architecture

```text
User question
    |
    v
React chat interface
    |
    v
FastAPI backend
    |
    +--> Finance domain guard and typo correction (NLP)
    |       |
    |       +--> Out-of-scope / unsafe request: safe redirect and suggestions
    |
    +--> Finance question: Tavily trusted-web retrieval
                    |
                    v
         Finance entities + ranked source evidence
                    |
                    v
     MySQL chat and retrieval-evidence storage
                    |
                    v
 Gemini Risk Agent / Orchestrator Agent integration point
```

## 3. Information Retrieval implementation

- **Primary retrieval service:** Tavily Search API.
- **Retrieval purpose:** obtain current, source-linked financial evidence rather than relying only on local documents.
- **Trusted-domain allow-list:**
  - Central Bank of Sri Lanka (CBSL)
  - Securities and Exchange Commission of Sri Lanka (SEC Sri Lanka)
  - Colombo Stock Exchange (CSE)
  - Consumer Financial Protection Bureau (CFPB)
  - Investor.gov
  - Federal Reserve
  - International Monetary Fund (IMF)
  - World Bank
- **Returned evidence:** source title, URL, text snippet, relevance score, and detected finance entities.
- **Default result size:** three sources, with support for one to five results in the shared UI.
- **Optional fallback modes:** local TF-IDF document retrieval and Gemini-based modes remain available for future use.

## 4. NLP techniques implemented

### Query preprocessing

- Token extraction and lowercasing.
- Stop-word removal for a cleaner retrieval query.
- Finance-focused query normalisation.

### Explainable entity extraction / rule-based NER

The NLP module identifies finance concepts such as:

- `LOAN` — loan, borrowing, repayment, credit, mortgage, debt
- `INTEREST_RATE` — interest, APR, rate of return
- `INVESTMENT` — investment, portfolio, shares, stocks, bonds, cryptocurrency
- `SAVINGS` — savings, fixed deposits, emergency fund
- `BUDGETING` — budget, income, expenses, spending, cash flow
- `FINANCIAL_PROTECTION` — insurance, fraud, scam, financial planning
- `RISK_TYPE` — market, credit, liquidity, concentration, repayment, and interest-rate risk
- `MONEY` and `PERCENT`

If spaCy is available, the module can also extract standard entities such as organisations, dates, money, percentages, and locations.

### Finance typo correction

Before classification and web retrieval, the system conservatively corrects likely finance typos. The original question remains unchanged in chat history, while only the retrieval query is corrected.

Examples:

| User text | Retrieval correction |
| --- | --- |
| `loen` / `laon` | `loan` |
| `intrest` | `interest` |
| `invesment` | `investment` |
| `savngs` | `savings` |
| `budjet` | `budget` |

The system informs the user when a correction was used, for example: `loen -> loan`.

## 5. Responsible AI: finance-domain guard

An explainable rule-based guard runs before Tavily is called.

| Request category | System behaviour |
| --- | --- |
| Financial education question | Retrieves trusted financial evidence. |
| Non-finance question | Does not use external retrieval; explains the scope and offers finance suggestions. |
| Gambling/betting financial-risk question | Gives safe financial-harm and debt-awareness guidance. |
| Betting tips, odds, predictions, or strategies | Declines the request and redirects to safe financial-risk questions. |

This improves scope transparency, reduces unnecessary API usage, and avoids encouraging harmful gambling behaviour.

## 6. Shared frontend and backend

### Frontend

- **Technology:** React, Vite, HTML, CSS, and JavaScript.
- ChatGPT-style financial research interface.
- Chat-history sidebar.
- Dark and light themes.
- Retrieved evidence cards with links, source domains, and relevance scores.
- Clickable suggested questions for new users and domain-guard redirects.
- Clear educational-use disclaimer.

### Backend

- **Technology:** Python, FastAPI, SQLAlchemy, and PyMySQL.
- Provides REST API endpoints for chats and messages.
- Calls the IR/NLP module for in-scope questions.
- Saves chat history and structured retrieval evidence.
- Automatically creates missing database tables during application startup.
- Loads secrets from ignored `.env` files; keys and passwords are not hard-coded.

## 7. MySQL data structure

```text
users
  └── chats
        └── messages
              └── retrieval_runs
                    └── retrieval_evidence
```

The data model preserves:

- User ID support for Taniya's future authentication work.
- Multiple questions per chat.
- Original user questions.
- Corrected retrieval queries when a finance typo is detected.
- NLP entities, retrieval engine, evidence snippets, source URLs, and relevance scores.

## 8. Multi-agent integration handoff

This module supplies structured evidence for the other team members:

```text
Adi's IR + NLP Agent
    -> trusted evidence and URLs
    -> Mahee's Gemini Risk Analysis Agent
    -> Shaji's Orchestrator / Decision-Making Agent
    -> Taniya's Authentication and Security Agent
```

The Gemini Risk Agent should use the retrieved evidence to produce an evidence-grounded risk explanation and summary. The IR module intentionally does not generate final financial advice.

## 9. Verification completed

- Tavily retrieval successfully returns source-linked evidence.
- FastAPI chat API and MySQL connection flow were tested.
- React production build completed successfully.
- Domain guard tests passed for:
  - finance questions
  - non-finance questions
  - gambling-risk education requests
  - restricted betting requests
- Typo-correction tests passed, including preservation of the original stored user question.

## 10. How to run the current system

### Backend terminal

From the project root, with the Python virtual environment activated:

```powershell
python -m uvicorn Backend.B1:app --reload
```

### Frontend terminal

```powershell
cd Frontend
npm run dev
```

Open the frontend URL shown by Vite, normally:

```text
http://localhost:5173
```

## 11. Security notes

- API keys and MySQL passwords must stay in `.env` files only.
- `.env`, `node_modules`, and React build outputs are excluded from Git.
- Current `user_id` support is prepared for integration with authentication.
- Before deployment, the Security Agent should add login/JWT authentication, per-user authorization, input validation, rate limiting, consent, data-retention controls, and secure production secret management.

## 12. Git commit

The completed implementation was committed as:

```text
8d9d6dd feat: add FinAssist IR, NLP, chat history, and React UI
```
