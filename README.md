# BOT GPT — Backend Setup

A conversational AI backend built with Django REST Framework.

---

## What's Built So Far

- Django project created with `django-admin startproject`
- `conversations` app created with `python manage.py startapp`
- PostgreSQL configured (via `.env` file)
- Django REST Framework + Swagger UI wired up
- Models: `Conversation`, `Message`, `Document`, `DocumentChunk`
- All API endpoints defined (LLM not connected yet — placeholder responses)
- Django Admin configured for all models
- Migrations generated with `python manage.py makemigrations`

---

## Project Structure

```
botgpt/
├── .env                        ← your local environment variables
├── requirements.txt            ← all Python dependencies
├── manage.py                   ← Django CLI
├── botgpt/
│   ├── settings.py             ← project settings (DRF, Swagger, Postgres)
│   ├── urls.py                 ← root URL config
│   └── wsgi.py
└── conversations/
    ├── models.py               ← Conversation, Message, Document, DocumentChunk
    ├── serializers.py          ← DRF serializers
    ├── views.py                ← API ViewSets (register, login, conversations, messages, docs)
    ├── urls.py                 ← URL router
    ├── admin.py                ← Django admin config
    └── migrations/
        └── 0001_initial.py     ← generated migration
```

---

## Tech Stack

| What | Tool |
|---|---|
| Language | Python 3.13 |
| Package manager | `uv` |
| Web framework | Django 4.2 |
| API layer | Django REST Framework |
| API docs | drf-spectacular (Swagger UI) |
| Database | SQLite (local file, zero setup) |
| Auth | DRF Token Authentication |

---

## Local Setup

### 1. Install dependencies

```bash
uv pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env .env.local   # already created, just edit DB values
```

Your `.env` file:
```
DEBUG=True
SECRET_KEY=django-insecure-change-me-in-production
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=botgpt_db
DB_USER=botgpt_user
DB_PASSWORD=botgpt_password
DB_HOST=localhost
DB_PORT=5432
```

### 3. Run migrations

```bash
uv run python manage.py migrate
```

### 5. Create admin user (optional)

```bash
uv run python manage.py createsuperuser
```

### 6. Start the server

```bash
uv run python manage.py runserver
```

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register new user, get token |
| POST | `/api/auth/login/` | Login, get token |
| POST | `/api/conversations/` | Start a new conversation |
| GET | `/api/conversations/` | List all your conversations |
| GET | `/api/conversations/{id}/` | Get conversation + messages |
| DELETE | `/api/conversations/{id}/` | Delete a conversation |
| POST | `/api/conversations/{id}/messages/` | Send a message |
| GET | `/api/conversations/{id}/messages/list/` | List all messages |
| POST | `/api/conversations/{id}/documents/` | Upload a PDF |
| GET | `/api/conversations/{id}/documents/list/` | List uploaded documents |

All endpoints (except register/login) require:
```
Authorization: Token <your-token>
```

---

## Swagger UI

After running the server, open:
```
http://localhost:8000/api/docs/
```

---

## Django Admin

```
http://localhost:8000/admin/
```

---

## What's Coming Next

- [ ] LLM service (Groq API — Llama 3, free)
- [ ] Context manager (sliding window token trimming)
- [ ] RAG service (PDF → chunks → ChromaDB → retrieval)
- [ ] Unit tests
- [ ] Dockerfile + docker-compose
- [ ] GitHub Actions CI/CD
