import os
import sqlite3
import ollama
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

app = FastAPI()

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
    conn = sqlite3.connect("ai_chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            plan TEXT DEFAULT 'free'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prompt TEXT,
            ai_reply TEXT,
            model TEXT,
            tokens INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO users (username, plan) VALUES ('Hari', 'pro')")
    cursor.execute("INSERT OR IGNORE INTO users (username, plan) VALUES ('Karan', 'free')")
    conn.commit()
    conn.close()

init_db()

class ChatMessage(BaseModel):
    sender: str
    prompt: str
    model: str = "qwen2.5:1.5b"

class NewUser(BaseModel):
    username: str
    plan: str

class PlanUpdate(BaseModel):
    plan: str

def stream_ai_and_save(user_id: int, user_prompt: str, model_name: str):
    conn = sqlite3.connect("ai_chat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prompt, ai_reply FROM history
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 5
    """, (user_id,))
    past_rows = cursor.fetchall()
    conn.close()

    conversation = [
        {"role": "system", "content": "You are a helpful assistant."}
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

    conn = sqlite3.connect("ai_chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO history (user_id, prompt, ai_reply, model, tokens)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, user_prompt, full_reply, model_name, len(full_reply)))
    conn.commit()
    conn.close()

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.post("/chat_with_ai")
def handle_ai_chat(msg: ChatMessage):
    conn = sqlite3.connect("ai_chat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, plan FROM users WHERE username = ?", (msg.sender,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    premium_models = ["llama3", "llama3:8b", "mistral"]
    if msg.model in premium_models and user["plan"] != "pro":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to use this model")

    return StreamingResponse(
        stream_ai_and_save(user["id"], msg.prompt, msg.model),
        media_type="text/plain"
    )

@app.get("/chats/{username}")
def get_user_chats(username: str):
    conn = sqlite3.connect("ai_chat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT users.username, users.plan, history.prompt, history.ai_reply, history.model, history.tokens
        FROM history
        INNER JOIN users ON history.user_id = users.id
        WHERE users.username = ?
    """, (username,))
    rows = cursor.fetchall()
    conn.close()
    return {"user": username, "all_chats": [dict(row) for row in rows]}

@app.post("/register")
def register_user(user: NewUser):
    conn = sqlite3.connect("ai_chat.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, plan) VALUES (?, ?)", (user.username.strip(), user.plan))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists!")
    conn.close()
    return {"status": "user_created", "username": user.username, "plan": user.plan}

@app.put("/users/{username}/plan")
def update_user_plan(username: str, update_data: PlanUpdate):
    conn = sqlite3.connect("ai_chat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET plan = ? WHERE username = ?", (update_data.plan, username))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    return {"status": "plan_updated", "username": username, "new_plan": update_data.plan}

@app.delete("/chats/{username}")
def clear_user_chats(username: str):
    conn = sqlite3.connect("ai_chat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    cursor.execute("DELETE FROM history WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "cleared", "deleted_for": username}