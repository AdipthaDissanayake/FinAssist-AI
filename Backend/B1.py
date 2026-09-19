"""FinAssist shared backend: MySQL chat history and IR/NLP integration.

Run from the project root after setting DATABASE_URL and TAVILY_API_KEY:
    python -m uvicorn Backend.B1:app --reload

Taniya's Security Agent must provide verified JWT identity before deployment.
Until then, chats are unowned development records (`user_id` is NULL).
"""

from __future__ import annotations

import os
import re
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .database import get_database_session, initialise_database
from .models import AnalysisUsageEvent, Chat, Message, Plan, RetrievalEvidence, RetrievalRun
from .subscription_routes import get_verified_user_id, router as subscription_router
from .subscription_service import (
    MonthlyAnalysisLimitReachedError,
    PlanNotAvailableError,
    SubscriptionServiceError,
    can_perform_analysis,
    complete_reserved_analysis,
    get_active_subscription,
    get_current_period_usage,
    get_remaining_monthly_analyses,
    release_reserved_analysis,
    reserve_analysis,
)
from IR_NLP_Agent.NLP.N1 import DomainAssessment, FinanceNLP
from Orchestrator_Agent.O1 import AgentWorkflowError, orchestrate_financial_question

from .auth_routes import router as auth_router
from .auth import get_current_user, get_current_user_optional
from .models import User
from Security_Agent.S1 import InputSanitizer, PromptInjectionGuard, SafeLogger, SecurityHeadersMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIRECTORY = PROJECT_ROOT / "Frontend"
FRONTEND_BUILD_DIRECTORY = FRONTEND_DIRECTORY / "dist"

# Load local development credentials before creating the retrieval client.  The
# root file is preferred; the IR-specific file remains a temporary fallback
# while the team consolidates configuration.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "IR_NLP_Agent" / ".env")
finance_nlp = FinanceNLP()


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=5)


app = FastAPI(title="FinAssist AI", version="0.2.0")
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(subscription_router)
app.include_router(auth_router)

if FRONTEND_BUILD_DIRECTORY.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_BUILD_DIRECTORY / "assets"), name="react-assets")


@app.on_event("startup")
def create_database_tables() -> None:
    initialise_database()


@app.get("/", include_in_schema=False)
def serve_application() -> FileResponse:
    index_file = FRONTEND_BUILD_DIRECTORY / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="React frontend is not built. Run `npm install` and `npm run build` in Frontend, or use `npm run dev`.",
        )
    return FileResponse(index_file)


@app.get("/api/health")
def health(database: Session = Depends(get_database_session)) -> dict[str, str]:
    database.execute(select(Chat.id).limit(1))
    return {"status": "ok", "service": "finassist-chat-backend", "database": "connected"}


@app.get("/api/chats")
def list_chats(
    database: Session = Depends(get_database_session),
    current_user: User | None = Depends(get_current_user_optional),
) -> list[dict[str, Any]]:
    if current_user:
        chats = database.scalars(
            select(Chat).where(Chat.user_id == current_user.id).order_by(desc(Chat.updated_at))
        ).all()
    else:
        chats = database.scalars(select(Chat).order_by(desc(Chat.updated_at))).all()
    return [_chat_payload(database, chat) for chat in chats]


@app.post("/api/chats", status_code=status.HTTP_201_CREATED)
def create_chat(
    request: ChatCreateRequest, 
    database: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    chat = Chat(user_id=current_user.id, title=_clean_title(request.title) or "New financial question")
    database.add(chat)
    database.commit()
    database.refresh(chat)
    return _chat_payload(database, chat)


@app.get("/api/chats/{chat_id}/messages")
def list_messages(chat_id: str, database: Session = Depends(get_database_session)) -> dict[str, Any]:
    chat = _require_chat(database, chat_id)
    messages = database.scalars(select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at)).all()
    return {"chat": _chat_payload(database, chat), "messages": [_message_payload(database, message) for message in messages]}


@app.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, database: Session = Depends(get_database_session)) -> Response:
    chat = _require_chat(database, chat_id)
    database.delete(chat)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
def add_message(
    chat_id: str,
    request: MessageCreateRequest,
    database: Session = Depends(get_database_session),
    user_id: str = Depends(get_verified_user_id),
) -> dict[str, Any]:
    """Store a question and run the IR → Risk Analysis agent workflow."""
    chat = _require_chat(database, chat_id)

    # 1. Security Layer: Input sanitization & control character scrubbing
    sanitization = InputSanitizer.sanitize_financial_query(request.content)
    cleaned_input = sanitization.cleaned_text

    # 2. Security Layer: Direct Prompt Injection Inspection
    injection_check = PromptInjectionGuard.inspect_query(cleaned_input)

    corrected_query, spelling_corrections = finance_nlp.correct_finance_spelling(cleaned_input)
    domain_assessment = finance_nlp.assess_domain(corrected_query)
    user_message = Message(
        chat_id=chat.id,
        role="user",
        content=cleaned_input,
        extra_data={
            "domain_assessment": domain_assessment.to_dict(),
            "spelling_corrections": spelling_corrections,
            "retrieval_query": corrected_query if spelling_corrections else None,
            "security_flags": injection_check.reasons if not injection_check.is_safe else [],
        },
    )
    database.add(user_message)
    if chat.title == "New financial question":
        chat.title = _clean_title(cleaned_input, 80)
    chat.updated_at = datetime.now(UTC)
    database.commit()
    database.refresh(user_message)

    if not injection_check.is_safe:
        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content="I detected instructions attempting to alter system security rules or request unauthorized actions. Please ask a standard financial research question.",
            extra_data={
                "agent": "security-guard",
                "security_flags": injection_check.reasons,
                "retrieval_skipped": True,
            },
        )
        database.add(assistant_message)
        database.commit()
        database.refresh(assistant_message)
        return {
            "user_message": _message_payload(database, user_message),
            "assistant_message": _message_payload(database, assistant_message),
        }

    if not domain_assessment.retrieval_allowed:
        content, suggested_questions, agent_tag = _domain_guard_response(domain_assessment, cleaned_input)
        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content=content,
            extra_data={
                "agent": agent_tag,
                "domain_assessment": domain_assessment.to_dict(),
                "suggested_questions": suggested_questions,
                "retrieval_skipped": True,
            },
        )
        database.add(assistant_message)
        database.commit()
        database.refresh(assistant_message)
        return {
            "user_message": _message_payload(database, user_message),
            "assistant_message": _message_payload(database, assistant_message),
        }

    try:
        has_remaining_quota = can_perform_analysis(database, user_id)
        existing_usage_event = database.scalar(
            select(AnalysisUsageEvent.id).where(AnalysisUsageEvent.message_id == user_message.id)
        )
        if not has_remaining_quota and existing_usage_event is None:
            database.commit()
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=_subscription_limit_response(database, user_id),
            )
        try:
            # Reservation remains authoritative even after a negative pre-check:
            # an existing message ID may be safely retried without consuming a
            # second allowance.
            reserve_analysis(database, user_id, user_message.id)
        except MonthlyAnalysisLimitReachedError:
            database.commit()
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=_subscription_limit_response(database, user_id),
            )
        # Persist the reservation before any Tavily, Gemini, or agent work.
        database.commit()
    except PlanNotAvailableError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscription plans are temporarily unavailable.",
        ) from exc
    except SubscriptionServiceError as exc:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The subscription service is temporarily unavailable.",
        ) from exc

    try:
        workflow = orchestrate_financial_question(corrected_query, top_k=request.top_k)
        retrieval = workflow["retrieval"]
    except AgentWorkflowError as exc:
        release_reserved_analysis(database, user_id, user_message.id)
        failure = RetrievalRun(
            message_id=user_message.id,
            status="failed",
            error_message=str(exc),
            query_entities=[],
        )
        database.add(failure)
        database.flush()
        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content="I could not complete the source-backed risk analysis. Please try again shortly.",
            extra_data={"agent": "orchestrator", "retrieval_run_id": failure.id},
        )
        database.add(assistant_message)
        database.commit()
        database.refresh(assistant_message)
        return {
            "user_message": _message_payload(database, user_message),
            "assistant_message": _message_payload(database, assistant_message),
        }
    except Exception:
        # The reservation was committed before external work.  Release it even
        # for an unexpected orchestration failure so it does not consume quota.
        release_reserved_analysis(database, user_id, user_message.id)
        database.commit()
        raise

    complete_reserved_analysis(database, user_id, user_message.id)

    retrieval_run = RetrievalRun(
        message_id=user_message.id,
        processed_query=retrieval.get("processed_query"),
        query_entities=retrieval.get("query_entities", []),
        retrieval_engine=retrieval.get("engine", "tavily-trusted-web-search"),
        status="completed",
    )
    database.add(retrieval_run)
    database.flush()
    for item in retrieval.get("evidence", []):
        database.add(
            RetrievalEvidence(
                retrieval_run_id=retrieval_run.id,
                text=item.get("text") or "",
                source_title=item.get("source") or "Unknown source",
                source_url=item.get("url"),
                relevance_score=item.get("score"),
                entities=item.get("entities", []),
            )
        )

    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=_workflow_success_message(workflow, spelling_corrections),
        extra_data={
            "agent": "orchestrator",
            "retrieval_run_id": retrieval_run.id,
            "agent_trace": workflow["agent_trace"],
            "risk_analysis": workflow["risk_analysis"],
            "decision_support": workflow.get("decision_support"),
            "spelling_corrections": spelling_corrections,
        },
    )
    database.add(assistant_message)
    database.commit()
    database.refresh(assistant_message)
    return {"user_message": _message_payload(database, user_message), "assistant_message": _message_payload(database, assistant_message)}


def _require_chat(database: Session, chat_id: str) -> Chat:
    chat = database.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    # TODO Taniya: check chat.user_id against the authenticated user's subject.
    return chat


def _chat_payload(database: Session, chat: Chat) -> dict[str, Any]:
    preview = database.scalar(
        select(Message.content).where(Message.chat_id == chat.id).order_by(desc(Message.created_at)).limit(1)
    )
    return {
        "id": chat.id,
        "user_id": chat.user_id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
        "preview": preview or "",
    }


def _message_payload(database: Session, message: Message) -> dict[str, Any]:
    metadata = dict(message.extra_data or {})
    retrieval_run_id = metadata.get("retrieval_run_id")
    if retrieval_run_id:
        retrieval_run = database.get(RetrievalRun, retrieval_run_id)
        if retrieval_run:
            metadata["retrieval"] = _retrieval_payload(database, retrieval_run)
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "role": message.role,
        "content": message.content,
        "metadata": metadata,
        "created_at": message.created_at.isoformat(),
    }


def _retrieval_payload(database: Session, retrieval_run: RetrievalRun) -> dict[str, Any]:
    evidence = database.scalars(
        select(RetrievalEvidence)
        .where(RetrievalEvidence.retrieval_run_id == retrieval_run.id)
        .order_by(RetrievalEvidence.created_at)
    ).all()
    return {
        "id": retrieval_run.id,
        "processed_query": retrieval_run.processed_query,
        "query_entities": retrieval_run.query_entities,
        "engine": retrieval_run.retrieval_engine,
        "status": retrieval_run.status,
        "evidence": [
            {
                "id": item.id,
                "text": item.text,
                "score": item.relevance_score,
                "source": item.source_title,
                "url": item.source_url,
                "entities": item.entities,
            }
            for item in evidence
        ],
    }


def _clean_title(value: str | None, limit: int = 160) -> str:
    return " ".join((value or "").split())[:limit].rstrip()


def _subscription_limit_response(database: Session, user_id: str) -> dict[str, Any]:
    """Build the quota response from the persisted subscription plan state."""

    subscription = get_active_subscription(database, user_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The active subscription could not be resolved.",
        )
    plan = database.get(Plan, subscription.plan_code)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The active subscription plan could not be resolved.",
        )
    used = get_current_period_usage(database, user_id)
    remaining = get_remaining_monthly_analyses(database, user_id)
    return {
        "error": "subscription_limit_reached",
        "message": "Monthly analysis limit reached.",
        "plan": plan.code,
        "used": used,
        "limit": plan.monthly_analysis_limit,
        "remaining": remaining,
    }


_GREETING_PATTERNS = (
    re.compile(r"^h+[i!]+$"),
    re.compile(r"^h+[e]+y+$"),
    re.compile(r"^h+[e]+l+[o]+$"),
    re.compile(r"^h+o+w+d+y+$"),
    re.compile(r"^h+i+y+a+$"),
    re.compile(r"^s+u+p+$"),
    re.compile(r"^y+o+$"),
)

_GREETING_WORDS = frozenset(
    {
        "hi", "hii", "hiii", "hello", "hey", "heyy", "hiya", "howdy",
        "greetings", "sup", "yo", "morning", "evening", "afternoon",
        "welcome", "gm", "gn", "hola",
    }
)

_GREETING_PHRASES = frozenset(
    {
        "good morning", "good afternoon", "good evening", "good day", "good night",
        "hi there", "hello there", "hey there", "how are you", "how are you doing",
        "how do you do", "how r u", "what is up", "whats up", "what's up",
        "how is it going", "hows it going", "how's it going", "nice to meet you",
        "pleased to meet you", "hi finassist", "hello finassist", "hey finassist",
        "how can i help you", "how can i help you today", "how can i help",
        "how can you help me", "how can you help", "how can you help me today",
        "what can you do", "what can you do for me", "what can you help with",
        "what can you help me with", "what can i ask", "what can i ask you",
        "what can i do here", "how does this work", "how do you work",
        "how to use this", "who are you", "what are you", "tell me about yourself",
        "introduce yourself", "what is finassist", "what is finassist ai",
        "what is this", "what is this app", "help", "help me", "start",
    }
)


def _is_greeting(text: str) -> bool:
    """Return True if the input is a greeting or general conversational hello."""
    cleaned = re.sub(r"[^\w\s]", "", (text or "").strip().lower())
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return False
    if cleaned in _GREETING_PHRASES or cleaned in _GREETING_WORDS:
        return True
    for pat in _GREETING_PATTERNS:
        if pat.match(cleaned):
            return True
    words = cleaned.split()
    if len(words) <= 4 and any(
        w in _GREETING_WORDS or any(p.match(w) for p in _GREETING_PATTERNS)
        for w in words
    ):
        return True
    for phrase in _GREETING_PHRASES:
        if cleaned.startswith(phrase):
            return True
    return False


def _domain_guard_response(
    assessment: DomainAssessment,
    query: str = "",
) -> tuple[str, list[dict[str, str]], str]:
    """Return transparent, useful guardrail messages without an API call.

    Returns:
        (content, suggested_questions, agent_tag)
    """
    if assessment.category == "gambling-risk":
        return (
            "Betting or gambling can affect a budget through losses, overspending, debt, and pressure to chase losses. "
            "FinAssist can support financial-harm awareness and debt-management questions, but it does not provide betting tips, odds, predictions, or strategies.",
            [
                "How can betting affect my budget and financial wellbeing?",
                "How can I manage gambling-related debt?",
                "How can I protect my savings while managing gambling spending?",
            ],
            "finance-domain-guard",
        )
    if assessment.category == "restricted-gambling":
        return (
            "FinAssist cannot provide betting tips, predictions, odds, or gambling strategies. "
            "It can help with the financial risks of betting, budget impact, savings protection, or gambling-related debt.",
            [
                "What are the financial risks associated with betting?",
                "How can betting affect my budget and financial wellbeing?",
                "How can I manage gambling-related debt?",
            ],
            "finance-domain-guard",
        )

    # 1. Greeting message
    if _is_greeting(query):
        return (
            "👋 Hello! Welcome to FinAssist AI.\n\n"
            "I am your specialized financial research and risk analysis assistant. "
            "I can help you evaluate financial decisions, assess investment and loan risks, and analyze financial topics using evidence from trusted regulatory and market sources.\n\n"
            "Here is what you can ask me about:\n"
            "• 🏦 Loans & Mortgages — Repayment risks, interest rate impacts, debt management\n"
            "• 📈 Investments & Markets — Stock & bond risk analysis, diversification, ETF evaluation\n"
            "• 💰 Savings & Budgeting — Fixed deposits, emergency funds, cash flow planning\n"
            "• 💱 Currency & Forex — Exchange rates, inflation risks, central bank policies\n"
            "• 🛡️ Financial Protection — Scam identification, consumer protection, credit risk\n\n"
            "Ask any financial question to get started, or choose one of the suggested topics below:",
            [
                "What are the risks of taking a personal loan?",
                "How does diversification reduce investment risk?",
                "What should I consider before opening a fixed deposit?",
                "How do interest rate hikes affect loan repayments?",
            ],
            "greeting-assistant",
        )

    # 2. Non-financial topic message
    return (
        "ℹ️ I can only assist with financial research and education.\n\n"
        "Your question does not appear to be related to finance, investing, or economics. "
        "As a dedicated financial AI assistant, my retrieval and risk analysis models are specifically designed for financial topics.\n\n"
        "You can ask me questions about:\n"
        "• 📊 Investments & Markets (stocks, bonds, mutual funds, portfolio risk)\n"
        "• 🏦 Loans & Borrowing (mortgages, personal loans, interest rates, debt)\n"
        "• 💵 Personal Finance (budgeting, emergency savings, fixed deposits)\n"
        "• 🌐 Economics & Forex (inflation, currency exchange, treasury bills)\n"
        "• 🛡️ Consumer Protection (financial scams, credit risk, fraud awareness)\n\n"
        "Please try asking a financial research question, or select one of the suggested topics below:",
        [
            "What are the risks of taking a loan?",
            "What is concentration risk in investing?",
            "How can I create a personal budget?",
            "What are the financial risks associated with betting?",
        ],
        "finance-domain-guard",
    )


def _workflow_success_message(workflow: dict[str, Any], spelling_corrections: list[dict[str, str]]) -> str:
    """Return Mahee's final analysis, noting any transparent query correction."""

    response = str(workflow["final_response"])
    if not spelling_corrections:
        return response
    changes = ", ".join(f"{item['from']} -> {item['to']}" for item in spelling_corrections)
    return f"I searched using the likely finance correction: {changes}.\n\n{response}"
