markdown


# FinAssist-AI 📈🤖
> **Multi-Agent AI System for Source-Grounded Financial Information Retrieval, Risk Analysis, Decision Support, and Security.**
FinAssist-AI is an end-to-end multi-agent financial research assistant that combines Natural Language Processing (NLP), live Information Retrieval (IR) from trusted financial institutions, LLM-powered evidence-grounded risk reasoning (Google Gemini), prompt security defenses, actionable decision support, and a complete commercial subscription & quota allowance management system.
---
## 🏛️ System Architecture & Multi-Agent Ecosystem
FinAssist-AI operates through specialized autonomous agents collaborating over strict JSON/HTTP API contracts:
┌────────────────────────────────────────────────────────┐ │ User Input (Web Client) │ └───────────────────────────┬────────────────────────────┘ ▼ ┌────────────────────────────────────────────────────────┐ │ 🛡️ Security Agent │ │ • Prompt injection filtering & jailbreak defense │ │ • System prompt leakage protection │ └───────────────────────────┬────────────────────────────┘ ▼ ┌────────────────────────────────────────────────────────┐ │ 🔍 Information Retrieval (IR) + NLP Agent (Adi) │ │ • Financial entity extraction & domain classification │ │ • Finance-specific spelling correction │ │ • Live evidence retrieval from trusted financial orgs │ └───────────────────────────┬────────────────────────────┘ ▼ ┌────────────────────────────────────────────────────────┐ │ ⚠️ Risk Analysis Agent (Mahee) │ │ • Grounded reasoning using Google Gemini │ │ • Risk severity breakdown (High / Medium / Low) │ │ • Strict evidence citation verification ([Evidence: E#])│ └───────────────────────────┬────────────────────────────┘ ▼ ┌────────────────────────────────────────────────────────┐ │ 💡 Decision Support Agent │ │ • Practical considerations & tradeoff analysis │ │ • Actionable financial decision checklist │ └───────────────────────────┬────────────────────────────┘ ▼ ┌────────────────────────────────────────────────────────┐ │ 🎼 Orchestrator Agent │ │ • Multi-agent coordination & full traceability pipeline│ │ • Executive risk summary & response formatting │ └────────────────────────────────────────────────────────┘



---
## 🚀 Core Modules & Agent Documentation
### 1. 🔍 [Information Retrieval + NLP Agent](IR_NLP_Agent/README.md)
- **Finance NLP**: Performs tokenization, financial entity recognition, and domain validation.
- **Finance Spelling Correction**: Auto-corrects domain-specific typos (e.g., `"fixd depost"` → `"fixed deposit"`).
- **Evidence Retrieval**: Uses Tavily API to search curated financial institutions (e.g., Central Banks, SEC, IMF, Credit Bureaus).
- **Fallback**: Local document store retrieval when offline.
### 2. ⚠️ [Risk Analysis Agent](Risk_Agent/README.md)
- **Evidence-Grounded Reasoning**: Uses Google Gemini to identify financial risks purely grounded in retrieved evidence.
- **Anti-Hallucination Filtering**: Automatically strips claims citing nonexistent sources.
- **Severity Scoring**: Categorizes risks with explicit justifications (High, Medium, Low).
### 3. 💡 Decision Support Agent
- Synthesizes risk findings into structured decision factors.
- Provides actionable checklists and key questions to evaluate before executing financial decisions.
### 4. 🛡️ Security Agent
- **Adversarial Filtering**: Blocks prompt injection attempts, persona hijacking, and instruction overrides.
- **Persona Preservation**: Enforces safety policies and non-circumventable educational disclaimers.
### 5. 🎼 [Orchestrator Agent](Orchestrator_Agent/README.md)
- Coordinates the end-to-end execution flow.
- Generates the executive summary, structured risk ranking, grounded citations, and full audit traces.
### 6. 💳 Subscription & Quota Allowance System
- **Tiered Plans**:
  - **Free Starter**: 5 analyses / month (LKR 0)
  - **Basic Pro**: 50 analyses / month (LKR 499)
  - **Premium Unlimited**: 200 analyses / month (LKR 999)
- **Payment Verification**: Masked card management (Visa, Mastercard, Amex, Discover) with Luhn checksum validation and simulated checkout.
- **Allowance Tracking**: Atomic quota reservation, completion, release on workflow errors, and usage history logs.
---
## 🛠️ Tech Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Pydantic, Uvicorn
- **Database**: MySQL / SQLite (with automatic schema creation and migrations)
- **AI & Retrieval**: Google Gemini API, Tavily Search API
- **Frontend**: React 18, Vite, Lucide Icons, Pure Responsive CSS
- **Authentication**: JWT authentication with Google OAuth (GIS) and Email/Password
---
## 📦 Getting Started
### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- (Optional) MySQL Server 8.0+
---
### 1. Backend Setup
1. **Activate Virtual Environment**:
   ```powershell
   # Windows
   .\venv\Scripts\Activate.ps1
   # macOS/Linux
   source venv/bin/activate
Install Dependencies:

bash


python -m pip install -r IR_NLP_Agent/requirements.txt
python -m pip install -r Backend/requirements.txt
Configure Environment Variables: Create a .env file in the project root:

env


# Database connection
DATABASE_URL=mysql+pymysql://finassist_app:password@localhost:3306/finassist_ai
# (For local testing without MySQL, you can use SQLite: sqlite:///test.db)
# AI & Search APIs
GEMINI_API_KEY=your_google_gemini_api_key
TAVILY_API_KEY=your_tavily_api_key
# JWT Secret
JWT_SECRET_KEY=your_secure_random_jwt_secret
Start the Backend Server:

bash


python -m uvicorn Backend.B1:app --reload --port 8000
ℹ️ The backend automatically creates all required database tables (users, chats, messages, subscriptions, payment_methods, analysis_usage_events, etc.) upon startup.

2. Frontend Setup
Navigate to Frontend Directory:

bash


cd Frontend
Install Dependencies:

bash


npm install
Start Development Server:

bash


npm run dev
Open your browser and navigate to http://localhost:5173.

🧪 Running Automated Tests
Run the complete test suites:

bash


# Run Backend unit & payment tests (33 tests)
python -m unittest discover -s Backend
# Run Multi-Agent End-to-End integration tests (5 tests)
python -m unittest discover -s tests
# Build Frontend production bundle
cd Frontend && npm run build
