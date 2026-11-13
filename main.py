import os
import psycopg2
import ollama
import time
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

app = FastAPI()

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "super-secret-dev-key")

def verify_api_key(x_api_key: str = Header(default=None)):
    """Rejects any request missing a matching X-API-KEY header with 401 Unauthorized."""
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-KEY header"
        )
    return x_api_key

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60
request_timestamps: dict[str, list[float]] = {}

def check_rate_limit(username: str):
    """Rejects users who exceed RATE_LIMIT_MAX requests within RATE_LIMIT_WINDOW seconds."""
    now = time.time()
    user_history = request_timestamps.get(username, [])
    valid_timestamps = [t for t in user_history if now - t < RATE_LIMIT_WINDOW]

    if len(valid_timestamps) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded! Maximum 5 messages per minute."
        )
    valid_timestamps.append(now)
    request_timestamps[username] = valid_timestamps

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://suhail:password456@localhost:5432/ai_chat_db"
)

def get_db_connection():
    """Returns a PostgreSQL connection where rows behave like Python dictionaries."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dynamic Ollama host for Docker networking
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
ollama_client = ollama.Client(host=OLLAMA_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            plan TEXT DEFAULT 'free'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            prompt TEXT NOT NULL,
            ai_reply TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens INTEGER NOT NULL
        )
    """)
    cursor.execute("""
        INSERT INTO users (username, plan)
        VALUES ('Suhail', 'pro'), ('Karan', 'free')
        ON CONFLICT (username) DO NOTHING
    """)
    conn.commit()
    conn.close()

init_db()

PERSONAS = {
    "default": "You're a helpful, concise AI assistant.",
    "coder": "You are a strict Senior Backend Engineer. Review code critically, point out edge cases, and always follow PEP 8 and production best practices.",
    "linux": "You are a veteran Linux System Administrator. Answer with practical bash commands, flags, and terminal explanations.",
    "pirate": "You are a 17th-century pirate captain. Answer every technical question in heavy pirate slang while still being accurate."
}

class ChatMessage(BaseModel):
    sender: str
    prompt: str
    model: str = "qwen2.5:1.5b"
    persona: str = "default"

class NewUser(BaseModel):
    username: str
    plan: str

class PlanUpdate(BaseModel):
    plan: str

def stream_ai_and_save(user_id: int, user_prompt: str, model_name: str, persona_key: str = "default"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prompt, ai_reply FROM history
        WHERE user_id = %s
        ORDER BY id DESC LIMIT 5
    """, (user_id,))
    past_rows = cursor.fetchall()
    conn.close()

    system_instruction = PERSONAS.get(persona_key, PERSONAS["default"])
    conversation = [
        {"role": "system", "content": system_instruction}
    ]
    for row in reversed(past_rows):
        conversation.append({"role": "user", "content": row["prompt"]})
        conversation.append({"role": "asssistant", "content": row["ai_reply"]})

    conversation.append({"role": "user", "content": user_prompt})

    full_reply = ""
    stream = ollama_client.chat(
        model=model_name,
        messages=conversation,
        stream=True
    )
    for chunk in stream:
        token = chunk["message"]["content"]
        full_reply += token
        yield token

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO history (user_id, prompt, ai_reply, model, tokens)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, user_prompt, full_reply, model_name, len(full_reply)))
    conn.commit()
    conn.close()

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.post("/chat_with_ai")
def handle_ai_chat(msg: ChatMessage, api_key: str = Depends(verify_api_key)):
    check_rate_limit(msg.sender)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, plan FROM users WHERE username = %s", (msg.sender,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    premium_models = ["llama3", "llama3:8b", "mistral"]
    if msg.model in premium_models and user["plan"] != "pro":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to use this model")

    return StreamingResponse(
        stream_ai_and_save(user["id"], msg.prompt, msg.model, msg.persona),
        media_type="text/plain"
    )

@app.get("/chats/{username}")
def get_user_chats(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT users.username, users.plan, history.prompt, history.ai_reply, history.model, history.tokens
        FROM history
        INNER JOIN users ON history.user_id = users.id
        WHERE users.username = %s
    """, (username,))
    rows = cursor.fetchall()
    conn.close()
    return {"user": username, "all_chats": [dict(row) for row in rows]}

@app.post("/register")
def register_user(user: NewUser):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, plan) VALUES (%s, %s)", (user.username.strip(), user.plan))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists!")
    conn.close()
    return {"status": "user_created", "username": user.username, "plan": user.plan}

@app.put("/users/{username}/plan")
def update_user_plan(username: str, update_data: PlanUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET plan = %s WHERE username = %s", (update_data.plan, username))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    return {"status": "plan_updated", "username": username, "new_plan": update_data.plan}

@app.delete("/chats/{username}")
def clear_user_chats(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    cursor.execute("DELETE FROM history WHERE user_id = %s", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "cleared", "deleted_for": username}