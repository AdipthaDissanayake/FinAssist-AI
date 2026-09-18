# FinAssist-AI 📈🤖

> **Multi-Agent AI System for Source-Grounded Financial Information Retrieval, Risk Analysis, Decision Support, and Security.**

FinAssist-AI is an end-to-end multi-agent financial research assistant that combines Natural Language Processing (NLP), live Information Retrieval (IR) from trusted financial institutions, LLM-powered evidence-grounded risk reasoning using Google Gemini, prompt security defenses, actionable decision support, and a complete commercial subscription and quota allowance management system.

---

## 🏛️ System Architecture & Multi-Agent Ecosystem

FinAssist-AI operates through specialized autonomous agents collaborating over strict JSON/HTTP API contracts.

```text
┌────────────────────────────────────────────────────────────┐
│                    User Input (Web Client)                 │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│ 🛡️ Security Agent                                         │
│ • Prompt injection filtering & jailbreak defense           │
│ • System prompt leakage protection                         │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│ 🔍 Information Retrieval (IR) + NLP Agent (Adi)            │
│ • Financial entity extraction & domain classification       │
│ • Finance-specific spelling correction                     │
│ • Live evidence retrieval from trusted financial orgs      │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Risk Analysis Agent (Mahee)                             │
│ • Grounded reasoning using Google Gemini                   │
│ • Risk severity breakdown (High / Medium / Low)            │
│ • Strict evidence citation verification ([Evidence: E#])   │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│ 💡 Decision Support Agent                                  │
│ • Practical considerations & tradeoff analysis             │
│ • Actionable financial decision checklist                  │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│ 🎼 Orchestrator Agent                                      │
│ • Multi-agent coordination & full traceability pipeline    │
│ • Executive risk summary & response formatting             │
└────────────────────────────────────────────────────────────┘
```

---

## 🚀 Core Modules & Agent Documentation

### 1. 🔍 Information Retrieval + NLP Agent

📁 [IR_NLP_Agent/README.md](IR_NLP_Agent/README.md)

- **Finance NLP:** Performs tokenization, financial entity recognition, and domain validation.
- **Finance Spelling Correction:** Automatically corrects domain-specific typos.

  Example:

  ```text
  "fixd depost" → "fixed deposit"
  ```

- **Evidence Retrieval:** Uses the Tavily API to search curated financial institutions, including central banks, the SEC, IMF, and credit bureaus.
- **Fallback:** Local document store retrieval when offline.

### 2. ⚠️ Risk Analysis Agent

📁 [Risk_Agent/README.md](Risk_Agent/README.md)

- **Evidence-Grounded Reasoning:** Uses Google Gemini to identify financial risks based on retrieved evidence.
- **Anti-Hallucination Filtering:** Automatically filters claims that cite nonexistent or unverifiable sources.
- **Severity Scoring:** Categorizes risks as High, Medium, or Low with explicit justifications.

### 3. 💡 Decision Support Agent

- Synthesizes risk findings into structured decision factors.
- Provides actionable checklists and key questions to evaluate before making financial decisions.
- Supports informed decision-making without presenting guaranteed investment outcomes.

### 4. 🛡️ Security Agent

- **Adversarial Filtering:** Blocks prompt injection attempts, persona hijacking, and instruction overrides.
- **Persona Preservation:** Enforces safety policies and non-circumventable educational disclaimers.
- **Prompt Security:** Helps protect system instructions and maintain safe agent behavior.

### 5. 🎼 Orchestrator Agent

📁 [Orchestrator_Agent/README.md](Orchestrator_Agent/README.md)

- Coordinates the end-to-end execution flow.
- Integrates specialized agents through structured API contracts.
- Generates executive summaries, structured risk assessments, grounded citations, and full audit traces.

### 6. 💳 Subscription & Quota Allowance System

FinAssist-AI includes a tiered subscription and usage allowance management system.

#### 📊 Subscription Plans

| Plan | Monthly Allowance | Price |
|---|---:|---:|
| 🆓 Free Starter | 5 analyses / month | LKR 0 |
| 💼 Basic Pro | 50 analyses / month | LKR 499 |
| ⭐ Premium Unlimited | 200 analyses / month | LKR 999 |

> **Note:** The Premium Unlimited plan provides 200 analyses per month, subject to the configured quota limits.

#### 💳 Payment Verification

- Masked card management.
- Support for Visa, Mastercard, American Express, and Discover.
- Luhn checksum validation.
- Simulated checkout and payment verification.

#### 📈 Allowance Tracking

- Atomic quota reservation.
- Analysis completion tracking.
- Quota release when workflow errors occur.
- Usage history and event logging.
- Subscription and allowance management.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| **Database** | MySQL / SQLite |
| **Database Management** | Automatic schema creation and migrations |
| **AI & Retrieval** | Google Gemini API, Tavily Search API |
| **Frontend** | React 18, Vite, Lucide Icons, Responsive CSS |
| **Authentication** | JWT Authentication, Google OAuth (GIS), Email/Password |
| **API Communication** | JSON/HTTP API Contracts |

---

## 📦 Getting Started

### Prerequisites

Ensure the following software is installed on your system:

- Python 3.11+
- Node.js 18+ and npm
- (Optional) MySQL Server 8.0+

---

### 1. Backend Setup

#### Step 1: Clone the Repository

```bash
git clone https://github.com/AdipthaDissanayake/FinAssist-AI.git
cd FinAssist-AI
```

#### Step 2: Activate the Virtual Environment

**Windows (PowerShell):**

```powershell
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source venv/bin/activate
```

> If the virtual environment has not been created yet, create one using:
>
> ```bash
> python -m venv venv
> ```

#### Step 3: Install Dependencies

Install the Information Retrieval and NLP Agent dependencies:

```bash
python -m pip install -r IR_NLP_Agent/requirements.txt
```

Install the backend dependencies:

```bash
python -m pip install -r Backend/requirements.txt
```

#### Step 4: Configure Environment Variables

Create a `.env` file in the project root directory.

```env
# Database Connection
DATABASE_URL=mysql+pymysql://finassist_app:password@localhost:3306/finassist_ai

# For local testing without MySQL, use SQLite:
# DATABASE_URL=sqlite:///test.db

# AI & Search APIs
GEMINI_API_KEY=your_google_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key

# JWT Secret
JWT_SECRET_KEY=your_secure_random_jwt_secret
```

> **Security Notice:**
>
> - Never commit your `.env` file to GitHub.
> - Add `.env` to your `.gitignore` file.
> - Use strong, randomly generated secrets for production.
> - Store API keys securely and never expose them in frontend code.

#### Step 5: Start the Backend Server

From the project root directory, run:

```bash
python -m uvicorn Backend.B1:app --reload --port 8000
```

The backend server will run at:

```text
http://localhost:8000
```

The backend automatically creates the required database tables upon startup, including:

- Users
- Chats
- Messages
- Subscriptions
- Payment Methods
- Analysis Usage Events
- Other required application tables

> Database initialization and migration behavior depend on the configured backend implementation and database settings.

---

### 2. Frontend Setup

#### Step 1: Navigate to the Frontend Directory

```bash
cd Frontend
```

#### Step 2: Install Frontend Dependencies

```bash
npm install
```

#### Step 3: Start the Development Server

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

Open the URL in your browser to access the FinAssist-AI web application.

---

## 🧪 Running Automated Tests

FinAssist-AI includes backend unit tests, payment-related tests, and multi-agent integration tests.

### 1. Run Backend Unit & Payment Tests

Run the backend test suite:

```bash
python -m unittest discover -s Backend
```

Expected test count:

```text
33 tests
```

### 2. Run Multi-Agent End-to-End Integration Tests

Run the integration test suite:

```bash
python -m unittest discover -s tests
```

Expected test count:

```text
5 tests
```

### 3. Build the Frontend Production Bundle

Navigate to the frontend directory:

```bash
cd Frontend
```

Run the production build:

```bash
npm run build
```

> **Testing Note:** The test counts above represent the expected test suite sizes. Run the commands to verify the current test results in your local environment.

---

## 🔐 Security & Responsible AI

FinAssist-AI is designed to support safer and more reliable financial information research.

### Security Features

- Prompt injection filtering.
- Jailbreak defense.
- System prompt leakage protection.
- Input validation and sanitization.
- JWT-based authentication.
- Google OAuth authentication.
- Secure API key management.
- Masked payment card information.
- Luhn checksum validation.
- Quota reservation and usage tracking.

### Responsible AI Principles

- Evidence-grounded financial information.
- Source citation and verification.
- Risk severity explanations.
- Clear distinction between information and financial advice.
- No guaranteed investment recommendations.
- Protection against unsafe or malicious inputs.
- Transparent multi-agent processing and audit traces.

> **Disclaimer:** FinAssist-AI is an educational financial research and decision-support system. Its outputs are not guaranteed financial advice or a substitute for professional financial guidance. Users should independently verify information and consider their own financial circumstances before making decisions.

---

## 📁 Project Structure

```text
FinAssist-AI/
│
├── Backend/
│   ├── B1.py
│   ├── requirements.txt
│   └── ...
│
├── Frontend/
│   ├── src/
│   ├── package.json
│   └── ...
│
├── IR_NLP_Agent/
│   ├── README.md
│   ├── requirements.txt
│   └── ...
│
├── Risk_Agent/
│   ├── README.md
│   └── ...
│
├── Orchestrator_Agent/
│   ├── README.md
│   └── ...
│
├── tests/
│   └── ...
│
├── .env
├── .gitignore
└── README.md
```

---

## 🌟 Key Features

- 🤖 Multi-agent financial research architecture.
- 🔍 Natural Language Processing and financial entity recognition.
- ✍️ Finance-specific spelling correction.
- 🌐 Live information retrieval from trusted financial sources.
- 🧠 Google Gemini-powered evidence-grounded reasoning.
- ⚠️ Financial risk identification and severity classification.
- 💡 Actionable decision support and tradeoff analysis.
- 🛡️ Prompt injection and jailbreak protection.
- 🔐 JWT and Google OAuth authentication.
- 💳 Subscription plans and quota management.
- 📊 Usage tracking and audit trails.
- 🖥️ Responsive React frontend.
- 🗄️ MySQL and SQLite database support.

---

## 👨‍💻 Contributors

FinAssist-AI is a collaborative academic project developed as part of the Information Retrieval and Web Analytics (IRWA) module.

| Contributor | Responsibility |
|---|---|
| **Adi** | Information Retrieval (IR) + NLP Agent |
| **Mahee** | Risk Analysis Agent |
| **Shajiwan** | Agent Architecture & Orchestration |
| **Taniya** | Security, Frontend & Responsible AI |

---

## 📄 License

This project is developed for academic and educational purposes.

Add your preferred license here if the repository is intended for open-source distribution.

---

## ⭐ Acknowledgements

- Google Gemini API
- Tavily Search API
- FastAPI
- React
- SQLAlchemy
- Pydantic
- Uvicorn
- MySQL
- SQLite

---

**FinAssist-AI — Intelligent Financial Information Retrieval, Risk Analysis, and Decision Support.** 📈🤖
