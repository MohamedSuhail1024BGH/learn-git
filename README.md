# Full-Stack Local AI Chat (FastAPI + SQLite + Ollama + Docker)

A containerized, multi-tiered AI chat application featuring Role-Based Access Control (RBAC), full relational CRUD operations, and real-time token streaming.

## Architecture & Features
- **Backend:** FastAPI with `StreamingResponse` for real-time LLM token streaming
- **Database:** Relational SQLite schema (`users` & `history` with Foreign Key constraints and `INNER JOIN` queries)
- **AI Engine:** Local LLM inference via Ollama (`qwen2.5:1.5b` / `llama3` / `mistral`)
- **Access Control:** Free vs. Pro tier enforcement (`HTTP 403 Forbidden` guard)
- **Containerization:** Docker & Docker Compose with persistent volume bind mounts

## Quick Start (Docker Compose)
1. Ensure [Ollama](https://ollama.com/) is running locally on port `11434`:
   ```bash
   ollama pull qwen2.5:1.5b