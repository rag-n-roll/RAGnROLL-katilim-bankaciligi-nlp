from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Katılım Bankacılığı Chatbot", version="0.1.0")


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
