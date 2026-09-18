# Domain Copilot — D3T5

**Variant:** D3 (Education — curriculum & assessment design) + T5 (Human review queue)

---

## Running the Project

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and **running**
- Git (to clone the repo)
- ~6 GB of free disk space (for the Ollama models)

> **Important — always `cd` into the project folder first.**
> Every `docker compose` command must be run from the directory containing `docker-compose.yml`.
> ```powershell
> cd e:\Domain-Copilot-FreshTest\Domain-Copilot
> ```

---

### Step 1 — Create your `.env` file

Copy the example and fill in the required values:

```powershell
Copy-Item .env.example .env   # Windows PowerShell
# or
cp .env.example .env          # macOS / Linux / Git Bash
```

Open `.env` and set these values:

| Variable | Required | Example value |
|---|---|---|
| `POSTGRES_USER` | ✅ | `postgres` |
| `POSTGRES_PASSWORD` | ✅ | `postgres` |
| `POSTGRES_DB` | ✅ | `domain_copilot` |
| `DATABASE_URL` | ✅ | `postgresql://postgres:postgres@postgres:5432/domain_copilot` |
| `VECTOR_STORE_URL` | ✅ | same as `DATABASE_URL` |
| `LLM_PROVIDER` | ✅ | `ollama` (local, free), `openai`, or `gemini` |
| `OPENAI_API_KEY` | Only if `openai` | your OpenAI key |
| `GEMINI_API_KEY` | Only if `gemini` | your Gemini API key |
| `OLLAMA_BASE_URL` | Optional | `http://ollama:11434` (Docker-internal) |
| `SECRET_KEY` | Optional in dev | any long random string |
| `APP_ENV` | Optional | `development` (auto-generates a JWT secret) |

---

### Step 2 — Pull the Ollama models **before** starting the API

> ⚠️ **This step must happen before `docker compose up` or before the API starts.**
> The API crashes at startup if the embedding model is missing — it pre-loads embeddings the moment it boots.

Start only Ollama and Postgres first:

```powershell
docker compose up -d postgres ollama
```

Wait ~10 seconds for Ollama to be ready, then pull both models:

```powershell
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3
```

`nomic-embed-text` is ~270 MB. `llama3` is ~4.7 GB. Wait for both to finish completely.

Verify they are installed:
```powershell
docker compose exec ollama ollama list
```

You should see both `nomic-embed-text` and `llama3` in the output.

---

### Step 3 — Start (or restart) the full stack

```powershell
docker compose up -d --build
```

All three containers should now start cleanly:
```
✔ Container domain-copilot-postgres-1  Running
✔ Container domain-copilot-ollama-1    Running
✔ Container domain-copilot-api-1       Running
```

---

### Step 4 — Run database migrations

```powershell
docker compose exec api python -m alembic upgrade head
```

This creates all the database tables (`document`, `chunk`, `users`, `review_task`, `published_curriculum`, etc.).

> Run this once after first setup, and again any time you pull new code that includes a migration.

---

### Step 5 — Seed the Database

Run this script to create the default users:
```powershell
docker compose exec api python backend/scripts/seed_users.py
```
This creates the following users you can log in with:
- **Instructor**: `instructor@example.com` / `password123`
- **Lead Instructor**: `lead@example.com` / `password123`

---

### Step 6 — Ingest Knowledge Base

Run this script to embed the curriculum documents into the vector database:
```powershell
docker compose exec api python backend/scripts/run_full_ingestion.py
```
*Note: This might take a few minutes if using local Ollama. With Gemini or OpenAI, it will be very fast.*

---

### Step 7 — Open the app

| What | URL |
|---|---|
| **Frontend UI** | http://localhost:8000 |
| **API health** | http://localhost:8000/health |
| **API ready check** | http://localhost:8000/ready |
| **Interactive API docs** | http://localhost:8000/docs |

---

## Everyday Commands

```powershell
# Check container status
docker compose ps

# View live logs from the API
docker compose logs -f api

# Stop everything (keeps database data)
docker compose down

# Stop and wipe all data (clean slate)
docker compose down -v

# Restart only the API (e.g. after a code change)
docker compose restart api

# Open a shell inside the API container
docker compose exec api bash
```

---

## Common Errors

### `api-1 exited with code 3` — `model "nomic-embed-text" not found`

The Ollama embedding model is not downloaded yet. Fix:

```powershell
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3
docker compose restart api
```

### `service "ollama" is not running`

You are running the command from the wrong directory. Make sure you are in the project root:

```powershell
cd e:\Domain-Copilot-FreshTest\Domain-Copilot
docker compose ps   # should show the containers
```

### `no configuration file provided: not found`

Same issue — wrong directory. `docker compose` looks for `docker-compose.yml` in the current folder.

### `service "api" is not running` when trying `alembic upgrade head`

The API container crashed at startup (usually the missing model error above). Fix the startup crash first, then run migrations.

---

## Using OpenAI Instead of Ollama

Set in `.env`:
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...your-key...
```

Then restart:
```powershell
docker compose restart api
```

You can skip the Ollama model pull steps entirely. The `ollama` container will still start (it's in `docker-compose.yml`) but the API won't use it.

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for C4 diagrams, the agentic workflow sequence diagram, ER diagram, and ADRs.