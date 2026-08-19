from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.main import router as data_api_router
from src.chatbot.rag_langchain import LangChainRAG

app = FastAPI(title="Katılım Bankacılığı Chatbot", version="0.1.0")
app.include_router(data_api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rag = LangChainRAG()


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
