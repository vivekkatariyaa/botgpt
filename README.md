# BOT GPT — Conversational AI Backend

A production-ready conversational AI backend built with Django REST Framework, supporting both open-ended chat and RAG (Retrieval-Augmented Generation) mode where responses are grounded in uploaded PDF documents.

---

## Features

- **Two conversation modes** — Open chat (general LLM) and RAG mode (answers grounded in your PDFs)
- **PDF ingestion pipeline** — Upload up to 3 PDFs per conversation (max 50 MB each), chunked and embedded using LangChain
- **Groq LLM integration** — Llama 3.3 70B via Groq API (fast, free tier)
- **Sliding-window context management** — Keeps token usage within limits using `tiktoken`
- **Retry logic** — Exponential backoff on LLM API failures using `tenacity`
- **Token authentication** — DRF Token Auth for all protected endpoints
- **Swagger UI** — Auto-generated interactive API docs via `drf-spectacular`
- **Streamlit frontend** — Simple chat UI on top of the REST API
- **Docker support** — Multi-stage Dockerfile for clean, portable builds
- **CI/CD** — GitHub Actions workflow that runs tests and validates the Docker build

---

## Tech Stack

| What | Tool |
|---|---|
| Language | Python 3.11 |
| Package manager | `uv` |
| Web framework | Django 4.2 + Django REST Framework |
| LLM | Groq API — Llama 3.3 70B |
| Vector store | ChromaDB (local persistent) |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` |
| PDF parsing | PyMuPDF via LangChain (`PyMuPDFLoader`) |
| Text chunking | LangChain `RecursiveCharacterTextSplitter` |
| Token counting | `tiktoken` |
| Retry logic | `tenacity` |
| Database | SQLite (dev) — swap to PostgreSQL for production |
| API docs | `drf-spectacular` (Swagger UI) |
| Frontend | Streamlit |
| Containerisation | Docker (multi-stage build) |
| CI/CD | GitHub Actions |

---

## Project Structure

```
botgpt/
├── .env                            ← local environment variables (never commit)
├── .github/workflows/ci.yml        ← GitHub Actions CI
├── .streamlit/config.toml          ← Streamlit config (upload size)
├── Dockerfile                      ← multi-stage Docker build
├── requirements.txt                ← Python dependencies
├── pytest.ini                      ← pytest config
├── manage.py
├── frontend.py                     ← Streamlit UI
├── design_doc/
│   └── architecture.md             ← full system design document
├── botgpt/
│   ├── settings.py                 ← Django settings (reads from .env)
│   ├── urls.py                     ← root URL config + Swagger
│   └── wsgi.py
└── conversations/
    ├── models.py                   ← Conversation, Message, Document, DocumentChunk
    ├── serializers.py              ← DRF serializers
    ├── views.py                    ← API ViewSets (auth, conversations, messages, docs)
    ├── urls.py                     ← URL router
    ├── admin.py                    ← Django admin config
    ├── migrations/
    │   └── 0001_initial.py
    ├── services/
    │   ├── chat_service.py         ← orchestrates a full chat turn
    │   ├── llm_service.py          ← Groq API calls + retry logic
    │   ├── rag_service.py          ← LangChain PDF ingestion + ChromaDB retrieval
    │   └── context_manager.py     ← sliding-window token management
    └── tests/
        ├── test_context_manager.py
        ├── test_llm_service.py
        └── test_api.py
```

---

## Local Setup

### 1. Install dependencies

```bash
uv pip install -r requirements.txt
```

### 2. Create your `.env` file

```env
DEBUG=True
SECRET_KEY=django-insecure-change-me-in-production
ALLOWED_HOSTS=localhost,127.0.0.1

GROQ_API_KEY=your-groq-api-key-here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_TOKENS=1024
CONTEXT_TOKEN_LIMIT=6000
CHROMA_PERSIST_DIR=./chroma_db
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

### 3. Run migrations

```bash
uv run python manage.py migrate
```

### 4. Create an admin user (optional)

```bash
uv run python manage.py createsuperuser
```

### 5. Start the Django server

```bash
uv run python manage.py runserver
```

### 6. Start the Streamlit frontend (separate terminal)

```bash
uv run streamlit run frontend.py
```

Open `http://localhost:8501` for the chat UI, or `http://localhost:8000/api/docs/` for the Swagger API docs.

---

## Docker

### Build

```bash
docker build -t botgpt .
```

### Run

```bash
docker run -p 8000:8000 --env-file .env botgpt
```

The server will be available at `http://localhost:8000`.

---

## Running Tests

```bash
uv run pytest
```

Tests cover:
- `ContextManager` — token counting, sliding window, RAG context injection
- `LLMService` — system prompt generation, mocked Groq API calls
- API endpoints — register, login, conversation CRUD, auth checks

---

## API Endpoints

All endpoints except `/auth/register/` and `/auth/login/` require:
```
Authorization: Token <your-token>
```

| Method | URL | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register a new user, returns token |
| POST | `/api/auth/login/` | Login, returns token |
| POST | `/api/conversations/` | Start a new conversation (`mode`: `open` or `rag`) |
| GET | `/api/conversations/` | List all your conversations |
| GET | `/api/conversations/{id}/` | Get conversation details + messages |
| DELETE | `/api/conversations/{id}/` | Delete a conversation |
| POST | `/api/conversations/{id}/messages/` | Send a message, get LLM reply |
| GET | `/api/conversations/{id}/messages/list/` | List all messages |
| POST | `/api/conversations/{id}/documents/` | Upload a PDF (RAG mode only) |
| GET | `/api/conversations/{id}/documents/list/` | List uploaded documents |

### Quick example

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

# Start a RAG conversation
curl -X POST http://localhost:8000/api/conversations/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "PDF Chat", "mode": "rag"}'

# Send a message
curl -X POST http://localhost:8000/api/conversations/<id>/messages/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"content": "What does the document say about pricing?"}'
```

---

## Useful Links (local)

| | URL |
|---|---|
| Swagger UI | `http://localhost:8000/api/docs/` |
| Django Admin | `http://localhost:8000/admin/` |
| Streamlit UI | `http://localhost:8501` |

---

## Notes

- SQLite is used for local development. For production, switch `DATABASES` in `settings.py` to PostgreSQL.
- ChromaDB and uploaded media files are stored locally and are excluded from git. They are ephemeral in Docker (reset on container restart) — use a volume mount or managed vector store for production.
- Image-based (scanned) PDFs are not supported — the RAG pipeline requires text-extractable PDFs.
