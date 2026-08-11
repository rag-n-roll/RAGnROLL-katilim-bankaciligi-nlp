from fastapi import FastAPI
from pydantic import BaseModel

from src.api.main import router as data_api_router

app = FastAPI(title="Katılım Bankacılığı Chatbot", version="0.1.0")
app.include_router(data_api_router)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return ChatResponse(reply=f"(placeholder) Mesajınızı aldım: {request.message}")
