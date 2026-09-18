# FinAssist AI - Application Security Architecture & Protection Report

## 1. Executive Summary & Security Objectives
FinAssist AI is a source-grounded financial intelligence and risk analysis platform combining Retrieval-Augmented Generation (RAG), Natural Language Processing (NLP), and multi-agent coordination with Google Gemini. 

Because financial systems handle sensitive decision-making data and interact with Large Language Models (LLMs), FinAssist AI implements a **Defense-in-Depth** security architecture designed to:
1. **Prevent Direct and Indirect Prompt Injection**: Protect system instructions from adversarial override and isolate untrusted external retrieved documents.
2. **Sanitize & Validate Inputs**: Enforce schema constraints, reject malicious payloads and null bytes, and encode outputs without altering legitimate financial symbols, mathematics, or questions.
3. **Protect Secrets & Sensitive Data**: Enforce strict key separation, irreversible password hashing (`bcrypt`), authenticated encryption at rest (`AES-256-GCM`), and automated credential/PII log redaction.
4. **Harden Network & API Boundaries**: Apply OWASP-recommended HTTP security headers, request size limits, and robust token authentication.

---

## 2. Threat Model & Attack Vectors

FinAssist AI addresses the primary risks defined in the **OWASP Top 10 for Large Language Model Applications**:

```
+-------------------------------------------------------------------------------+
|                             FINASSIST THREAT MODEL                            |
+------------------------------------+------------------------------------------+
| Threat Vector                      | Potential Impact                         |
+------------------------------------+------------------------------------------+
| LLM01: Direct Prompt Injection     | Adversary overrides system prompt via    |
|                                    | "ignore previous instructions" or DAN.   |
| LLM01: Indirect Prompt Injection   | Poisoned web search results or documents |
|                                    | contain hidden instructions for the LLM. |
| LLM06: Sensitive Info Disclosure   | System prompt, API keys, or internal     |
|                                    | configurations leaked in chat output.    |
| LLM09: Overreliance & Guarantees   | Model claims "100% guaranteed profit" or |
|                                    | provides unauthorized financial advice.  |
| XSS / Injection Attacks            | Malicious HTML/scripts in user inputs    |
|                                    | rendered unsafely in web browsers.       |
| Broken Authentication / Secrets    | Stolen JWT tokens, hardcoded API keys,   |
|                                    | or reversibly stored plaintext passwords.|
| Resource Exhaustion / DoS          | Oversized payloads causing memory strain |
|                                    | or excessive billable LLM API calls.     |
+------------------------------------+------------------------------------------+
```

---

## 3. Security Architecture & Agent Boundaries

Security is implemented as an independent, modular agent (`Security_Agent/S1.py`) that guards request entry points, agent-to-agent boundaries, and LLM output streams.

```
       [ Client / Web Browser ]
                  │
                  ▼
   ┌───────────────────────────────┐
   │   SecurityHeadersMiddleware   │  (CSP, HSTS, X-Frame-Options, 1MB Size Limit)
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │        InputSanitizer         │  (NFKC Normalization, Control/Null Char Scrubbing)
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │     PromptInjectionGuard      │  (Direct Injection Detection & Keyword Analysis)
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │         Backend (B1)          │  (JWT Auth, Subscription & Quota Enforcement)
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │       Orchestrator (O1)       │
   └──────────────┬────────────────┘
         ┌────────┴────────┐
         ▼                 ▼
   ┌───────────┐     ┌────────────────────────────────────────────────────────┐
   │ IR/NLP    │     │  Risk Analysis Agent (R1)                              │
   │ Agent     │────▶│  - Nonced XML Sandbox: <evidence_data_{nonce}>         │
   └───────────┘     │  - Gemini 3.6 Flash Generation                         │
                     │  - Output Auditor: Disallows leaks & guaranteed claims │
                     └────────────────────────────────────────────────────────┘
```

---

## 4. Key Security Controls & Implementation Details

### 4.1 Input Sanitization & Content Validation (`InputSanitizer`)
- **Non-Destructive Sanitization**: Standard financial queries contain mathematical operations, percentages, currency symbols (`$`, `€`, `£`, `Rs.`, `LKR`), and punctuation. `InputSanitizer` uses Unicode **NFKC normalization** and scrubs only non-printable control characters (`\x00-\x08`, `\x0B-\x1F`, `\x7F`).
- **Null-Byte Rejection**: Incoming payloads containing `\x00` are rejected immediately with `HTTP 400 Bad Request`.
- **Output Encoding (`SafeHTMLEncoder`)**: All user content rendered in browser environments is context-encoded via `html.escape` to neutralize `<script>` tags, event handlers, and iframe injection.

### 4.2 Encryption & Secret Management (`SecretManager`, `CryptoEngine`)
- **Strict Key Separation**: `JWT_SECRET_KEY` is isolated from third-party vendor keys (`GEMINI_API_KEY`, `TAVILY_API_KEY`, `GOOGLE_CLIENT_ID`).
- **Irreversible Password Storage**: Passwords are never reversibly encrypted; they are hashed with cryptographic salt using `bcrypt`.
- **Authenticated Encryption at Rest (`AES-256-GCM`)**: Reversible sensitive fields (e.g. transient OAuth tokens) use authenticated 256-bit AES-GCM encryption with randomized 96-bit nonces, ensuring data confidentiality and tamper detection.
- **Safe Logging (`SafeLogger`)**: All backend log streams automatically pass through redaction filters masking Bearer tokens, JWT strings, API keys, emails, passwords, and credit card numbers.

### 4.3 Multi-Layered Prompt Injection Protection (`PromptInjectionGuard`)

Prompt injection is defended across three distinct stages:

1. **Pre-Ingestion Heuristic Scanning**:
   - Detects instruction override patterns (`ignore previous instructions`, `bypass rules`, `disregard commands`).
   - Blocks jailbreak attempts (`DAN mode`, `unrestricted AI`, `developer mode`).
   - Flags system prompt exfiltration requests (`reveal system prompt`, `print hidden instructions`).

2. **Nonced Delimiter Sandboxing (Indirect Injection Defense)**:
   - External retrieved evidence from RAG/Tavily is treated as **untrusted data**.
   - Prompts sandbox evidence and user inputs in cryptographically unique XML tags with a per-request session nonce:
     ```xml
     <untrusted_user_input_8f2a9c1b>
     What are the risks of taking a loan?
     </untrusted_user_input_8f2a9c1b>

     <evidence_data_8f2a9c1b>
     [{"id": "1", "text": "...", "source": "Central Bank"}]
     </evidence_data_8f2a9c1b>
     ```
   - Nested delimiter breakout attempts inside retrieved web content (e.g. `</evidence_data>`) are automatically sanitized to `[/evidence_data]`.

3. **Post-Generation Output Auditing**:
   - Model responses are audited to verify that internal system prompts or confidential configuration rules were not leaked.
   - Unsupported guaranteed financial claims (e.g., "100% guaranteed profit", "zero risk guaranteed returns") are flagged and neutralized to maintain financial regulatory compliance.

---

## 5. Security Test Suite & Verification Results

The automated security test suite (`Security_Agent/test_security_agent.py`) verifies all 10 core security vectors:

```
+----+----------------------------------------------+--------------------+---------+
| #  | Security Test Case                           | Verification Focus | Result  |
+----+----------------------------------------------+--------------------+---------+
| 01 | Normal Financial Questions                   | Zero false positives on legitimate | PASSED  |
|    |                                              | questions with currency/math       |         |
| 02 | Empty & Oversized Inputs (>2,000 chars)      | Rejection with HTTP 400 and 413    | PASSED  |
| 03 | Malformed Payloads & Null Byte Injection     | Rejection of \x00 and invalid types| PASSED  |
| 04 | HTML / Script Injection & Context Encoding   | Neutralization of <script> and XSS | PASSED  |
| 05 | Direct Prompt Injection (Overrides & DAN)    | Detection and risk score >= 0.70   | PASSED  |
| 06 | Indirect RAG Document Injection              | Nonced delimiter sandbox isolation | PASSED  |
| 07 | System Prompt & Secret Exfiltration          | Pre-check blocking & output audit  | PASSED  |
| 08 | Credential & PII Log Redaction               | Redaction of JWT, API keys, emails | PASSED  |
| 09 | Malformed & Expired Authentication Tokens    | Rejection with HTTP 401            | PASSED  |
| 10 | Security Headers & AES-256-GCM Encryption    | CSP/HSTS headers & crypto AEAD     | PASSED  |
+----+----------------------------------------------+--------------------+---------+
```

### Full Project Test Summary:
- **Security Agent Tests**: **10 / 10 passed**
- **Authentication & Subscription Tests**: **26 / 26 passed**
- **Risk Analysis Agent Tests**: **16 / 16 passed**
- **Orchestrator Agent Tests**: **1 / 1 passed**
- **End-to-End Integration Tests**: **5 / 5 passed**
- **Total Project Tests**: **43 / 43 passed (100% Success Rate)**

---

## 6. Setup & Environment Configuration

Copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

Provide your deployment secrets:
```env
DATABASE_URL=mysql+pymysql://finassist_app:your_password@localhost:3306/finassist_ai
GEMINI_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=tvly-your_tavily_api_key_here
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
JWT_SECRET_KEY=secure_random_jwt_secret_key_at_least_32_characters
```

To generate a secure 256-bit `JWT_SECRET_KEY` in Python:
```python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 7. Residual Risks & Future Hardening
- **LLM Non-Determinism**: No heuristic scanner can guarantee 100% detection against novel adversarial prompt engineering. FinAssist AI relies on structural isolation (nonced XML sandboxing) as the primary defense rather than keyword blocking alone.
- **Rate Limiting**: For multi-tenant cloud deployments, deploying Redis-backed IP rate limiters (e.g., `slowapi`) is recommended to mitigate distributed denial of service (DDoS).
