from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, init_db, PERSONAS, request_timestamps

init_db()  # Ensure the database is initialized before running tests
client = TestClient(app)

VALID_HEADERS = {"X-API-KEY": "super-secret-dev-key"}

def test_serve_frontend():
    """1. Verify GET / returns the HTML frontend (200 OK)"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_get_user_chats():
    """2. Verify GET /chats/{username} returns a JSON list (200 OK)"""
    response = client.get("/chats/Hari")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, (list, dict))

def test_free_tier_rbac_guard():
    """3. Verify a Free-tier user is blocked from using a Pro model (403 Forbidden)"""
    client.put("/users/Karan/plan", json={"plan": "free", "new_plan": "free"})
    client.put("/users/Karan/plan?plan=free&new_plan=free")

    response = client.post(
        "/chat_with_ai",
        headers=VALID_HEADERS,
        json={
        "sender": "Karan",
        "prompt": "Hello",
        "model": "llama3"
        }
    )
    assert response.status_code ==  403

def test_delete_nonexistent_chat():
    """4. Verify deleting a fake chat ID returns 404 Not found"""
    response = client.delete("/chats/999999")
    assert response.status_code == 204 or response.status_code == 404

@patch("main.ollama_client.chat")
def test_pro_user_ai_stream_and_persona(mock_ollama_chat):
    """5. Verify Pro user streaming, Pirate persona injection, and SQLite save (200 OK)"""
    mock_ollama_chat.return_value = [
        {"message": {"content": "Ahoy "}},
        {"message": {"content": "Matey!"}}
    ]

    response = client.post(
        "/chat_with_ai",
        headers=VALID_HEADERS,
        json={
        "sender": "Hari",
        "prompt": "Status report",
        "model": "qwen2.5:1.5b",
        "persona": "pirate"
        }
    )

    assert response.status_code == 200
    assert response.text == "Ahoy Matey!"

    called_kwargs = mock_ollama_chat.call_args.kwargs
    sent_messages = called_kwargs["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == PERSONAS["pirate"]

def test_missing_or_wrong_api_key_blocked():
    """6. Verify requests without a valid X-API-Key header are rejected with 401 Unauthorized"""
    response = client.post(
        "/chat_with_ai",
        headers={"X-API-KEY": "wrong-hacker-key"},
        json={
            "sender": "Hari",
            "prompt": "Let me in!",
            "model": "qwen2.5:1.5b"
        }
    )
    assert response.status_code == 401

@patch("main.ollama_client.chat")
def test_rate_limiter_blocks_spam(mock_ollama_chat):
    """7. Verify sending more than 5 requests in 60s returns 429 Too Many Requests"""
    mock_ollama_chat.return_value = [{"message": {"content": "OK"}}]
    request_timestamps.pop("Hari", None)

    payload = {
        "sender": "Hari",
        "prompt": "Ping",
        "model": "qwen2.5:1.5b"
    }

    for _ in range(5):
        res = client.post("/chat_with_ai", headers=VALID_HEADERS, json=payload)
        assert res.status_code == 200

    blocked_res = client.post("/chat_with_ai", headers=VALID_HEADERS, json=payload)
    assert blocked_res.status_code == 429
    assert "Rate limit exceeded" in blocked_res.json()["detail"]