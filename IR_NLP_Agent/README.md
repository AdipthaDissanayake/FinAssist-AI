# FinAssist Information Retrieval + NLP Agent

This agent retrieves current, source-linked financial evidence using Tavily Search API, then passes it to the Risk Agent for Gemini-based analysis. The agent does not provide financial advice or generate the final risk analysis; that is the Risk Agent's responsibility.

## What it demonstrates

- NLP query preprocessing and explainable finance entity extraction.
- Conservative finance typo correction before domain classification and retrieval (for example, `loen` → `loan`), with the correction recorded transparently.
- An explainable finance-domain guard that avoids web search for unrelated questions.
- Safe financial-harm guidance for betting/gambling risks, while declining tips, odds, predictions, and strategies.
- Tavily web retrieval, which returns title, URL, snippet, and relevance score.
- A trusted-domain allow-list so financial evidence comes from regulators, central banks, stock exchanges, and international financial institutions.
- Structured JSON evidence for the Orchestrator Agent.
- Optional local TF-IDF and Gemini Embedding 2 retrieval if the team later chooses to use its own documents.
- A JSON response contract for the Orchestrator Agent.

## Primary mode: Tavily trusted web retrieval

1. Install dependencies: `python -m pip install -r IR_NLP_Agent/requirements.txt`
2. Create a Tavily API key, then set it privately in PowerShell:

```powershell
$env:TAVILY_API_KEY="your-key-here"
```

3. Run:

```powershell
python IR_NLP_Agent/main.py --engine tavily --query "What are the risks of putting savings into one investment?"
```

The agent searches approved domains by default: CBSL, SEC Sri Lanka, CSE, CFPB, Investor.gov, Federal Reserve, IMF, and World Bank. It prints evidence with a source title, URL, snippet, score, and NLP entities. It does not need locally collected PDFs.

To use a different approved set of domains, set a comma-separated allow-list before running:

```powershell
$env:TAVILY_INCLUDE_DOMAINS="cbsl.gov.lk,sec.gov.lk,cse.lk,imf.org,worldbank.org"
```

Do not put the API key in source code, GitHub, screenshots, or a report. The Security Agent should also reject unsafe inputs before sending them to Gemini.

### Local proxy troubleshooting

FinAssist uses direct HTTPS for Tavily by default because stale `HTTP_PROXY`,
`HTTPS_PROXY`, or `ALL_PROXY` variables can prevent web retrieval. If your
deployment intentionally uses a managed proxy, set
`TAVILY_USE_SYSTEM_PROXY=true` in its private environment.

## Gemini's role: risk reasoning and generation

Tavily is the Information Retrieval tool. Mahee's Risk Agent should give the resulting `evidence` list to Gemini and instruct Gemini to explain risks using only that evidence, cite its URLs, and include an educational-not-advice disclaimer.

## Optional Gemini Google Search (paid projects only)

Google Search grounding for standard Gemini Flash models is unavailable through the API on the Free tier. If the team enables billing, use:

```powershell
$env:GEMINI_MODEL="gemini-3.5-flash-lite"
python IR_NLP_Agent/main.py --engine gemini-search --query "What are the risks of taking a loan?"
```

## Optional local-document fallback

If the team later needs an offline mode, put permitted `.pdf`, `.txt`, or `.md` files in `Data/Raw/` and run:

```powershell
python IR_NLP_Agent/main.py --engine local --query "How can diversification lower investment risk?"
```

For semantic local retrieval, use `--engine gemini-embeddings`. This mode needs documents and the same API key. For additional general-purpose named-entity recognition, run `py -m pip install spacy`; the finance term, money, and percentage extraction already works without it.

Only upload documents that the team is allowed to process. Never include a user's account details, passwords, national ID, or transaction data in the knowledge base or query.

## Contract for Shaji's Orchestrator

Input:

```json
{"query": "What is interest-rate risk for borrowers?", "top_k": 5}
```

Output:

```json
{
  "query": "What is interest-rate risk for borrowers?",
  "engine": "tavily-trusted-web-search",
  "evidence": [
    {
      "text": "...",
      "score": 0.82,
      "source": "Central bank or regulator title",
      "url": "https://example.org/source",
      "page": null,
      "entities": [{"text": "interest rate", "label": "INTEREST_RATE"}]
    }
  ]
}
```

Shaji should send `evidence` unchanged to the Risk Agent so Mahee can ground the Gemini response in the displayed sources.
