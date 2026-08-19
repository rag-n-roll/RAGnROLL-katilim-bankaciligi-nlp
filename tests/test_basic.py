from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_rag_response(monkeypatch):
    monkeypatch.setattr(
        "src.main.rag.ask_question",
        lambda message: f"RAG yanıtı: {message}",
    )

    response = client.post("/chat", json={"message": "merhaba"})

    assert response.status_code == 200
    assert response.json() == {"reply": "RAG yanıtı: merhaba"}


def test_chat_requires_message_field():
    response = client.post("/chat", json={})
    assert response.status_code == 422
