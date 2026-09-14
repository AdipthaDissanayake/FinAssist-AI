"""FinAssist shared backend: MySQL chat history and IR/NLP integration.

Run from the project root after setting DATABASE_URL and TAVILY_API_KEY:
    python -m uvicorn Backend.B1:app --reload

Taniya's Security Agent must provide verified JWT identity before deployment.
Until then, chats are unowned development records (`user_id` is NULL).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .database import get_database_session, initialise_database
from .models import Chat, Message, RetrievalEvidence, RetrievalRun
from IR_NLP_Agent.main import retrieve_financial_evidence
from IR_NLP_Agent.NLP.N1 import DomainAssessment, FinanceNLP


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
    top_k: int = Field(default=3, ge=1, le=5)


app = FastAPI(title="FinAssist AI", version="0.2.0")
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
def list_chats(database: Session = Depends(get_database_session)) -> list[dict[str, Any]]:
    chats = database.scalars(select(Chat).order_by(desc(Chat.updated_at))).all()
    return [_chat_payload(database, chat) for chat in chats]


@app.post("/api/chats", status_code=status.HTTP_201_CREATED)
def create_chat(request: ChatCreateRequest, database: Session = Depends(get_database_session)) -> dict[str, Any]:
    # TODO Taniya: get the ID from verified JWT claims, never from the browser body.
    chat = Chat(user_id=None, title=_clean_title(request.title) or "New financial question")
    database.add(chat)
    database.commit()
    database.refresh(chat)
    return _chat_payload(database, chat)


@app.get("/api/chats/{chat_id}/messages")
def list_messages(chat_id: str, database: Session = Depends(get_database_session)) -> dict[str, Any]:
    chat = _require_chat(database, chat_id)
    messages = database.scalars(select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at)).all()
    return {"chat": _chat_payload(database, chat), "messages": [_message_payload(database, message) for message in messages]}


@app.post("/api/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
def add_message(
    chat_id: str, request: MessageCreateRequest, database: Session = Depends(get_database_session)
) -> dict[str, Any]:
    """Store a question and source-backed IR result.

    Shaji's Orchestrator can later replace this direct IR invocation. Mahee's
    Risk Agent should read `retrieval.evidence`, call Gemini, and store an
    independent analysis message without changing these IR tables.
    """
    chat = _require_chat(database, chat_id)
    corrected_query, spelling_corrections = finance_nlp.correct_finance_spelling(request.content.strip())
    domain_assessment = finance_nlp.assess_domain(corrected_query)
    user_message = Message(
        chat_id=chat.id,
        role="user",
        content=request.content.strip(),
        extra_data={
            "domain_assessment": domain_assessment.to_dict(),
            "spelling_corrections": spelling_corrections,
            "retrieval_query": corrected_query if spelling_corrections else None,
        },
    )
    database.add(user_message)
    if chat.title == "New financial question":
        chat.title = _clean_title(request.content, 80)
    chat.updated_at = datetime.now(UTC)
    database.commit()
    database.refresh(user_message)

    if not domain_assessment.retrieval_allowed:
        content, suggested_questions = _domain_guard_response(domain_assessment)
        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content=content,
            extra_data={
                "agent": "finance-domain-guard",
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
        retrieval = retrieve_financial_evidence(corrected_query, top_k=request.top_k, engine="tavily")
    except (RuntimeError, ValueError) as exc:
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
            content="I could not retrieve sources for this question. Please try again shortly.",
            extra_data={"agent": "information-retrieval", "retrieval_run_id": failure.id},
        )
        database.add(assistant_message)
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Source retrieval is temporarily unavailable. Please try again shortly.",
        ) from exc

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
        content=_retrieval_success_message(spelling_corrections),
        extra_data={
            "agent": "information-retrieval",
            "retrieval_run_id": retrieval_run.id,
            "next_agent": "risk-analysis",
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


def _domain_guard_response(assessment: DomainAssessment) -> tuple[str, list[dict[str, str]]]:
    """Return transparent, useful guardrail messages without an API call."""

    common_suggestions = [
        {"label": "Loan repayment risks", "question": "What are the risks of taking a loan?"},
        {"label": "Investment concentration risk", "question": "What is concentration risk in investing?"},
        {"label": "Create a personal budget", "question": "How can I create a personal budget?"},
    ]
    if assessment.category == "gambling-risk":
        return (
            "Betting or gambling can affect a budget through losses, overspending, debt, and pressure to chase losses. "
            "FinAssist can support financial-harm awareness and debt-management questions, but it does not provide betting tips, odds, predictions, or strategies.",
            [
                {"label": "Budget impact of betting", "question": "How can betting affect my budget and financial wellbeing?"},
                {"label": "Managing gambling-related debt", "question": "How can I manage gambling-related debt?"},
                {"label": "Protect emergency savings", "question": "How can I protect my savings while managing gambling spending?"},
            ],
        )
    if assessment.category == "restricted-gambling":
        return (
            "FinAssist cannot provide betting tips, predictions, odds, or gambling strategies. "
            "It can help with the financial risks of betting, budget impact, savings protection, or gambling-related debt.",
            [
                {"label": "Financial risks of betting", "question": "What are the financial risks associated with betting?"},
                {"label": "Budget impact of betting", "question": "How can betting affect my budget and financial wellbeing?"},
                {"label": "Managing gambling-related debt", "question": "How can I manage gambling-related debt?"},
            ],
        )
    return (
        "FinAssist focuses on financial education and research, so I did not search external sources for that topic. "
        "I can help with loans, savings, investments, budgets, interest rates, financial scams, and financial risks of betting.",
        common_suggestions
        + [{"label": "Financial risks of betting", "question": "What are the financial risks associated with betting?"}],
    )


def _retrieval_success_message(spelling_corrections: list[dict[str, str]]) -> str:
    """Tell the user when a finance-specific typo was corrected for retrieval."""

    if not spelling_corrections:
        return "I found source-backed financial evidence. The Risk Analysis Agent can now assess possible risks using these sources."
    changes = ", ".join(f"{item['from']} -> {item['to']}" for item in spelling_corrections)
    return (
        f"I searched using the likely finance correction: {changes}. "
        "I found source-backed financial evidence. The Risk Analysis Agent can now assess possible risks using these sources."
    )
