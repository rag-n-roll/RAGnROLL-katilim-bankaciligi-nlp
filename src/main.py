import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.main import router as data_api_router
from src.api.main import DEFAULT_DATABASE
from src.persistence import CampaignStore
from src.services import GroundedAssistant


def _enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).casefold() not in {
        "0",
        "false",
        "off",
        "hayır",
        "hayir",
    }


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Hazır Chroma varsa ilk kullanıcı isteğinden önce query modelini ısıtır."""

    if _enabled("RAGNROLL_EMBEDDING_WARMUP"):
        assistant = GroundedAssistant(
            CampaignStore(DEFAULT_DATABASE), chroma_enabled=True
        )
        vector = assistant.retriever.vector_retriever
        if vector is not None and vector.ready():
            try:
                await asyncio.to_thread(
                    vector.provider.embed_query, "katılım bankacılığı bilgi sorgusu"
                )
            except Exception:
                pass
            else:
                application.state.grounded_assistant = assistant
                rag._assistant = assistant
    yield


app = FastAPI(
    title="Katılım Bankacılığı Chatbot",
    version="0.1.0",
    lifespan=lifespan,
)
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
