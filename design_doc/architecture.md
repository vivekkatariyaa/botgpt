# BOT GPT — System Design Document

**Senior AI Engineer Case Study Submission**

---

## 1. Context & Problem Statement

BOT GPT is a production-grade conversational AI backend supporting:
- Internal enterprise assistants
- Customer-facing chatbots
- Multi-turn document-grounded workflows

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                          │
│                                                              │
│        Streamlit UI          Swagger UI / Postman            │
└───────────────────────────────────┬──────────────────────────┘
                                    │  HTTPS  REST
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                     API LAYER  —  Django REST Framework      │
│                                                              │
│   POST /auth/register        POST /conversations/{id}/messages│
│   POST /auth/login           POST /conversations/{id}/documents│
│   GET / POST / DELETE /conversations                         │
│                                                              │
│              Token Authentication  │  Swagger UI             │
└───────────────────────────────────┬──────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                     SERVICE LAYER                            │
│                                                              │
│   ┌─────────────────────────┐    ┌────────────────────────┐  │
│   │      ChatService        │    │       RAGService        │  │
│   │  (orchestrates a turn)  │    │  (LangChain pipeline)  │  │
│   └────────────┬────────────┘    └───────────┬────────────┘  │
│                │                             │               │
│   ┌────────────▼────────────┐    ┌───────────▼────────────┐  │
│   │      LLMService         │    │    ContextManager       │  │
│   │  Groq API  +  tenacity  │    │  tiktoken sliding window│  │
│   │  retry / backoff        │    │  + summarisation        │  │
│   └─────────────────────────┘    └────────────────────────┘  │
└───────────────────────────────────┬──────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                         │
│                                                              │
│      SQLite  (dev)  /  PostgreSQL  (prod)                   │
│      ┌──────────┐  ┌─────────────┐  ┌──────────────────┐   │
│      │   User   │  │ Conversation│  │ Message / Document│   │
│      └──────────┘  └─────────────┘  └──────────────────┘   │
│                                                              │
│      FAISS  (vector index — one per conversation)           │
│      ┌──────────────────────────────────────────────┐       │
│      │  PDF chunks  +  HuggingFace embeddings       │       │
│      └──────────────────────────────────────────────┘       │
└───────────────────────────────────┬─────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                 EXTERNAL  —  Groq API                        │
│                 Llama 3.3 70B  (free tier, fast inference)   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack Justification

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Django REST Framework | Deep familiarity; clean ViewSets, built-in auth, auto Swagger |
| **Database** | SQLite (dev) / PostgreSQL (prod) | Zero setup for dev; easy schema migration to Postgres |
| **Vector Store** | FAISS (CPU) | Lightweight, no external service, index saved/loaded from disk |
| **LLM** | Groq API — Llama 3.3 70B | Free, fastest inference provider, no credit card |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) | Free, runs locally, no API key |
| **PDF Parsing** | LangChain PyMuPDFLoader | Clean integration with LangChain pipeline |
| **Chunking** | LangChain RecursiveCharacterTextSplitter | Smartest splitter — paragraph → sentence → word |
| **Token counting** | tiktoken | Accurate BPE tokenizer for context budgeting |
| **Retry logic** | tenacity | Declarative exponential backoff on LLM errors |
| **Frontend** | Streamlit | Rapid UI — login, chat, PDF upload in ~300 lines |
| **CI/CD** | GitHub Actions | Native integration, free for public repos |
| **Container** | Docker | Reproducible environment |

---

## 4. Data Model & Schema

### Entity Relationship
```
User (Django built-in)
 └── Conversation (many)
      ├── Message (many, ordered by created_at)
      └── Document (many, max 3 per conversation)
           └── DocumentChunk (many, ordered by chunk_index)
```

### Conversation
```
id                UUID  PRIMARY KEY
user_id           FK → auth_user
title             VARCHAR(255)
mode              VARCHAR(10)   -- 'open' | 'rag'
is_active         BOOLEAN
total_tokens_used INTEGER
summary           TEXT
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ
```

### Message
```
id                UUID  PRIMARY KEY
conversation_id   FK → conversation  (CASCADE DELETE)
role              VARCHAR(20)   -- 'user' | 'assistant' | 'system'
content           TEXT
tokens_used       INTEGER
is_summary        BOOLEAN
created_at        TIMESTAMPTZ

-- Ordering: created_at ASC, id ASC (guaranteed FIFO)
```

### Document
```
id                UUID  PRIMARY KEY
conversation_id   FK → conversation  (CASCADE DELETE)
filename          VARCHAR(255)
file_path         FileField
file_size         INTEGER
status            VARCHAR(20)  -- 'pending' | 'processing' | 'ready' | 'failed'
chunk_count       INTEGER
error_message     TEXT
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ
```

### DocumentChunk
```
id                UUID  PRIMARY KEY
document_id       FK → document  (CASCADE DELETE)
chunk_text        TEXT
chunk_index       INTEGER
embedding_id      VARCHAR(255)   -- FAISS reference
UNIQUE(document_id, chunk_index)
```

---

## 5. REST API Design

### Authentication
```
POST /api/auth/register/   → { user, token }
POST /api/auth/login/      → { user, token }

All protected endpoints require:
Authorization: Token <token>
```

### Conversations (CRUD)
```
POST   /api/conversations/                    → 201 { id, title, mode, messages }
GET    /api/conversations/                    → 200 { count, next, previous, results: [...] }
GET    /api/conversations/{id}/               → 200 { id, messages, documents }
DELETE /api/conversations/{id}/               → 204
POST   /api/conversations/{id}/messages/      → 200 { id, role, content, tokens_used }
GET    /api/conversations/{id}/messages/list/ → 200 [ messages ]
POST   /api/conversations/{id}/documents/     → 201 { id, filename, chunk_count }
GET    /api/conversations/{id}/documents/list/→ 200 [ documents ]
```

**Pagination:** Offset-based, default page size 20. Response envelope includes `count`, `next`, and `previous` for standard DRF pagination. Cursor-based pagination would be preferred at scale (avoids COUNT(*) on large tables).

### HTTP Codes
| Code | Meaning |
|---|---|
| 201 | Created |
| 200 | Success |
| 204 | Deleted |
| 400 | Bad request / validation error |
| 401 | Not authenticated |
| 404 | Not found (also used for other-user's resources) |
| 422 | PDF processing failed |
| 503 | LLM service unavailable |

---

## 6. LLM Call Flow — Open Chat

```
POST /api/conversations/{id}/messages/ { content }
  │
  ▼
ConversationViewSet.send_message()
  │
  ▼
ChatService.handle_message()
  ├── Save user message (DB)
  ├── Fetch full history
  ├── ContextManager.build_context()
  │     └── Sliding window — keep newest msgs within token budget
  ├── LLMService.chat()
  │     ├── tenacity retry (3x on timeout/rate-limit)
  │     └── groq.chat.completions.create(model=llama-3.3-70b-versatile)
  ├── Save assistant reply + token count (DB)
  └── Return assistant Message
  │
  ▼
Response 200: { role: "assistant", content: "...", tokens_used: N }
```

---

## 7. RAG Flow — Grounded Chat

### Phase 1: Document Ingestion
```
POST /api/conversations/{id}/documents/ (PDF file)
  │
  ▼
Validation: PDF only, max 50MB, max 3 docs per conversation
  │
  ▼
RAGService.ingest_document()
  ├── PyMuPDFLoader      → load PDF pages
  ├── RecursiveCharacterTextSplitter → chunk (512 chars, 50 overlap)
  ├── HuggingFaceEmbeddings          → embed (all-MiniLM-L6-v2)
  └── FAISS.from_documents()         → store index on disk (per conversation)
  │
  ▼
Document status → "ready", chunk_count saved
```

### Phase 2: Grounded Message
```
POST /api/conversations/{id}/messages/ { content }
  │
  ▼
ChatService detects mode = "rag"
  │
  ▼
RAGService.retrieve(query, conversation_id)
  └── vectorstore.similarity_search(query, k=4) → top 4 chunks
  │
  ▼
ContextManager.build_context(
    system_prompt = RAG_SYSTEM_PROMPT,
    messages      = history,
    rag_context   = retrieved_chunks   ← injected between system + history
)
  │
  ▼
LLM answers grounded in document context
```

---

## 8. Context & Token Management

### Cost Framing
Groq's free tier eliminates inference cost entirely for this prototype. In production, every token sent to the LLM costs money — token-aware context trimming (sliding window + summarisation) directly reduces per-request cost by ensuring only the minimum necessary context is sent. At scale, this can cut LLM spend by 40–60% compared to naively sending the full history.

### Strategy
```
Available budget = CONTEXT_TOKEN_LIMIT(6000) - GROQ_MAX_TOKENS(1024) = 4976 tokens

Message priority (highest → lowest):
  1. System prompt        (always included)
  2. RAG context          (if RAG mode)
  3. Summary message      (if history was summarised)
  4. Recent messages      (sliding window — newest first)
```

### Sliding Window
Iterates history in reverse (newest → oldest), keeping messages that fit within budget and dropping older ones once the budget is exceeded. Token counts are tracked per message using `tiktoken` (cl100k_base encoding).

### Summarization
When `total_tokens_used > 80% of limit`:
- Older messages are summarised by the LLM in 3–5 sentences
- Summary stored as a single `[SUMMARY]` system message
- Old messages deleted — token counter reset

### Caching
Response caching is not implemented in this prototype. Semantic caching (e.g. GPTCache — cache LLM responses for semantically similar queries) is a planned enhancement that would further reduce cost and latency for repeated or near-duplicate questions.

---

## 9. Error Handling & Scalability

### Failure Handling
| Failure | Strategy |
|---|---|
| LLM timeout | tenacity retries 3× (2s, 4s, 8s backoff) |
| Token limit | Sliding window trims before API call |
| DB write failure | Django `transaction.atomic()` rollback |
| PDF image-only | Clear 422 error — user informed |
| File too large | 400 error before processing begins |
| Unauthorised access | 401/404 responses |

### Logging & Monitoring
All services use Python's standard `logging` module with named loggers per module. Logged events include: LLM call latency and token counts, RAG retrieval results, PDF ingestion progress, and all error tracebacks. In production, structured JSON logging would feed into a log aggregator (e.g. Datadog, Papertrail), and Sentry would capture unhandled exceptions with full context. Railway's built-in log stream provides sufficient visibility for the current prototype.

### Scalability at 1M Users
| Bottleneck | Solution |
|---|---|
| Django (CPU) | Horizontal scaling — multiple pods behind load balancer |
| SQLite → Postgres | Migrate to Postgres + read replicas |
| FAISS (single node) | Migrate to Qdrant / Weaviate / Pinecone (distributed) |
| LLM calls (latency) | Async task queue (Celery + Redis) |
| PDF ingestion (CPU heavy) | Background Celery worker — return 202 immediately |

---

## 10. Deployment & CI/CD

### Local
```bash
cp .env.example .env   # add GROQ_API_KEY
uv pip install -r requirements.txt
python manage.py migrate
python manage.py runserver        # API at :8000
streamlit run frontend.py         # UI at :8501
```

### Docker
```bash
docker build -t botgpt .
docker run -p 8000:8000 --env-file .env botgpt
```

### Unit Tests (22 tests across 3 files)
| File | What is tested |
|---|---|
| `test_context_manager.py` | Token counting accuracy, sliding window drops oldest messages when over budget, RAG context injected at correct position, summary message preserved |
| `test_llm_service.py` | System prompt content for open vs RAG mode, mocked Groq API returns correct reply and token count, correct model/messages passed to API |
| `test_api.py` | Register/login endpoints, conversation CRUD (create, list, retrieve, delete), send message flow, 401 on unauthenticated requests, 404 when accessing another user's conversation |

### CI/CD Pipeline (GitHub Actions)
```
On push to main:
  Job 1: test
    ├── pip install -r requirements.txt
    ├── python manage.py migrate
    └── pytest conversations/tests/ -v   ← 22 tests

  Job 2: docker (runs only after test passes)
    └── docker build -t botgpt:ci .
```

### Live Deployment (Railway)
| Service | URL |
|---|---|
| Django REST API + Swagger UI | https://botgpt.up.railway.app/api/docs/ |
| Django Admin | https://botgpt.up.railway.app/admin/ |
| Streamlit Chat UI | https://botogpt-vivek.up.railway.app |
| GitHub Repository | https://github.com/vivekkatariyaa/botgpt |

---

*BOT GPT — Senior AI Engineer Case Study*
