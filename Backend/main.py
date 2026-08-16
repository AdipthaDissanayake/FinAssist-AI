from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="FinAssist AI API",
    description="Backend API for the FinAssist AI agentic financial analysis system",
    version="1.0.0",
)

# Allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {
        "message": "FinAssist AI API is running",
        "status": "online",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "FinAssist AI Backend",
    }


@app.post("/api/analyze")
def analyze(request: AnalysisRequest):
    return {
        "status": "success",
        "question": request.question,
        "message": "Analysis pipeline received the request.",
        "agent": "orchestrator",
    }