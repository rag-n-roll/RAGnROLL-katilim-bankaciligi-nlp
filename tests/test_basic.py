from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_placeholder_response():
    response = client.post("/chat", json={"message": "merhaba"})
    assert response.status_code == 200
    body = response.json()
    assert "merhaba" in body["reply"]


def test_chat_requires_message_field():
    response = client.post("/chat", json={})
    assert response.status_code == 422
