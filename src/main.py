import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.main import router as data_api_router
from src.api.main import DEFAULT_DATABASE
from src.persistence import CampaignStore
from src.services import GroundedAssistant

app = FastAPI(title="Katılım Bankacılığı Chatbot", version="0.1.0")
app.include_router(data_api_router)
app.state.chroma_enabled = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        value.strip()
        for value in os.getenv(
            "RAGNROLL_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if value.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LocalChatFacade:
    """Ağır model yüklemeden structured-first yerel asistana erişir."""

    def __init__(self) -> None:
        self._assistant: GroundedAssistant | None = None

    def ask_question(self, message: str) -> str:
        if self._assistant is None:
            self._assistant = GroundedAssistant(
                CampaignStore(DEFAULT_DATABASE), chroma_enabled=True
            )
        return self._assistant.answer(message)["answer"]


rag = LocalChatFacade()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    answer = rag.ask_question(request.message)
    return ChatResponse(reply=answer)
