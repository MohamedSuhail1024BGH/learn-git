# [LEARN_GIT] Local AI Chat - Full-Stack FastAPI, SQLite, Ollama, Docker

![FastAPI Automated Test](https://github.com/MohamedSuhail1024BGH/learn-git/actions/workflows/test.yml/badge.svg)

A containerized full-stack AI chat application featuring live token streaming, multi-turn conversational memory, Role-Based Access Control (RBAC), and a multi-container Docker Compose setup.

## Architecture & Tech Stack
- **Backend API:** FastAPI (`main.py`) with `StreamingResponse` and `FileResponse`
- **Database & Memory:** SQLite (`ai_chat.db`) with Foreign Keys, `INNER JOIN`, and 5-turn sliding context window
- **LLM Engine:** Local Ollama inference
- **Containers:** Multi-container `docker-compose.yml` (`backend` on `:8000` + `sqlite-web` admin dashboard on `:8080`)
- **CI & Testing:** Automated `pytest` suite running on GitHub Actions (`ubuntu-24.04`)

## Quick Start (Docker Compose)
   ```bash
   docker compose up -d