# News summarization text tool

Fetches news into Postgres, builds an **Ollama**-powered **bullet digest** (and optional **PDF**), reindexes **RAG** (LangChain + pgvector) for the latest batch, and can deliver everything through **Telegram** (digest PDF + long-polling Q&A bot).

---

## What you need installed

| Requirement | Why |
|-------------|-----|
| **Python 3.12+** (3.14 works if dependencies install) | App runtime |
| **PostgreSQL** with **`pgvector`** | Articles + digest tables; vector store for RAG |
| **Ollama** running locally (default `http://127.0.0.1:11434`) | Digest summarization, embeddings, RAG chat |
| **Ollama models** | Chat: set via `OLLAMA_MODEL` (e.g. `llama3.2`). Embeddings: `nomic-embed-text` (default `OLLAMA_EMBED_MODEL`) |
| **PDF fonts** (not committed) | See [PDF fonts](#pdf-fonts-for-telegram-digest) |

Optional:

- **Telegram bot** from [@BotFather](https://t.me/BotFather) for digest + polling bot.
- **E\*TRADE API env vars** if you wire `app/users/e_trade_service.py` to real holdings; otherwise a fixed symbol list is used for finance rows.

---

## Setup

### 1. Clone and virtualenv

```bash
cd news-summarization-text-tool
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Postgres + `vector`

Create a database and enable the extension (superuser or allowed role):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Point the app at it with **`DATABASE_URL`** (see [Environment variables](#environment-variables)).

### 3. Ollama

```bash
ollama serve   # in a separate terminal, if not already a service
ollama pull nomic-embed-text
ollama pull <your-chat-model>   # must match OLLAMA_MODEL in .env, e.g. llama3.2
```

### 4. Environment file

Copy or create **`.env`** in the project root (same folder as `requirements.txt`). `python-dotenv` loads it automatically.

## PDF fonts for Telegram digest

Place these files under **`app/telegram/fonts/`** (see `app/telegram/fonts/FONTS.txt` for licenses and links):

- `DejaVuSans.ttf`
- `DejaVuSans-Bold.ttf`
- `NotoSansSymbols2-Regular.ttf`

Without them, PDF generation raises a clear error at send time.

### 5. Apply DB schema (first time)

```bash
cd /path/to/news-summarization-text-tool
source .venv/bin/activate
python -m app.db.ingest --init-schema --skip-fetch
```

`--skip-fetch` skips news fetch so you only apply `sql/schema.sql`.

---

## Environment variables

| Variable | Required for | Notes |
|----------|----------------|-------|
| **`DATABASE_URL`** | Ingest, RAG, digest storage | e.g. `postgresql://user:pass@localhost:5432/dbname` |
| **`OLLAMA_MODEL`** | Digest summarization, RAG answers, Telegram bot | Chat model name in Ollama |
| **`OLLAMA_BASE_URL`** | Ollama clients | Default `http://127.0.0.1:11434` |
| **`OLLAMA_EMBED_MODEL`** | RAG indexing / queries | Default `nomic-embed-text` |
| **`TELEGRAM_BOT_TOKEN`** | PDF digest + polling bot | From BotFather |
| **`TELEGRAM_CHAT_ID`** and/or **`TELEGRAM_ALLOWED_CHAT_IDS`** | Who receives the PDF; who may use the bot | Comma-separated IDs allowed; see `app/telegram/config.py` |
| **`RAG_COLLECTION_NAME`** | pgvector collection name | Optional; default `news_latest_batch` |
| E\*TRADE vars | Live portfolio symbols | Only if you implement OAuth in `e_trade_service.py` |

Get your numeric **chat id** by messaging the bot and inspecting `getUpdates`, or use `@userinfobot`.

---

## Ingestion CLI (`python -m app.db.ingest`)

Default run: **fetch news → upsert DB → Ollama digest → RAG reindex**. Telegram PDF is **off** unless you pass **`--telegram`**.

### Flags

| Flag | Effect |
|------|--------|
| **`--init-schema`** | Run `sql/schema.sql` (tables/indexes). Use for first setup or schema changes—not needed every cron run. |
| **`--skip-fetch`** | Exit after optional `--init-schema`; no `fetch_news`. |
| **`--limit-per-topic`** `N` | Max RSS-style articles per topic (default **5**). |
| **`--no-portfolio`** | Omit finance portfolio / per-symbol Yahoo/Google-style rows. |
| **`--portfolio-news`** `N` | Max headline rows per portfolio symbol (default **5**). |
| **`--portfolio-no-fulltext`** | Skip full article fetch for finance URLs (faster). |
| **`--no-summarize`** | Skip Ollama digest; **incompatible with `--telegram`**. |
| **`--no-rag-index`** | Skip pgvector reindex after ingest. |
| **`--print-digest`** | Print digest bullets to stdout (requires summarization). |
| **`--telegram`** | After digest, build PDF and **send to all configured Telegram chats** (requires summarization + fonts + token/chat ids). |

### Typical commands

**First-time schema + full pipeline (no Telegram):**

```bash
python -m app.db.ingest --init-schema
python -m app.db.ingest
```

**Daily run with digest log + Telegram PDF:**

```bash
python -m app.db.ingest --telegram --print-digest
```

**Faster finance pass:**

```bash
python -m app.db.ingest --portfolio-no-fulltext
```

---

## Telegram: digest PDF

1. Set **`TELEGRAM_BOT_TOKEN`**, **`TELEGRAM_CHAT_ID`** (and optionally **`TELEGRAM_ALLOWED_CHAT_IDS`**).
2. Install [PDF fonts](#pdf-fonts-for-telegram-digest).
3. Run ingest **with** summarization and **`--telegram`**:

```bash
python -m app.db.ingest --telegram
```

The bot calls **`getChat`** per recipient to personalize the greeting and caption; each chat gets its own PDF bytes. **`OLLAMA_MODEL`** must be set digest + RAG need the same Ollama stack.

---

## Telegram: RAG polling bot

Answers only from chats in **`TELEGRAM_ALLOWED_CHAT_IDS`** / **`TELEGRAM_CHAT_ID`**. Uses **`ask_latest_news`** (pgvector + `OLLAMA_MODEL`).

```bash
cd /path/to/news-summarization-text-tool
source .venv/bin/activate
python -m app.telegram poll
```

Requirements:

- Ingest has run at least once **with** RAG indexing (default on) so the vector store is not empty.
- **`OLLAMA_MODEL`**, **`DATABASE_URL`**, Telegram env as above.

Stop with **Ctrl+C** (or your process supervisor / cron stop pattern).

---

## RAG from the terminal (optional)

```bash
python -m app.rag ask "What happened in markets today?" -k 8
python -m app.rag ask "..." --json
```

**`-k`**: number of chunks to retrieve (default **8**). Requires a successful ingest with RAG indexing.

---

## Cron / automation tips

- Cron has a minimal environment: use **absolute paths** to `.venv/bin/python` and `cd` to the repo before `python -m app.db.ingest ...`.
- Redirect logs with a path whose **parent directory exists**, or `mkdir -p` that directory first.
- **`--init-schema`** on every scheduled run is usually unnecessary once the DB exists.

---

## Project layout (high level)

| Path | Role |
|------|------|
| `app/db/ingest.py` | Ingest CLI |
| `app/news/news.py` | RSS + finance fetch |
| `app/summarize/` | Ollama digest |
| `app/rag/` | Embeddings, index, `ask` CLI, query chain |
| `app/telegram/` | PDF, `notify`, `api`, `poll` bot |
| `sql/schema.sql` | Tables for articles + digest |

---

## Troubleshooting

| Issue | Things to check |
|-------|------------------|
| RAG / bot: “No indexed chunks” | Run ingest without `--no-rag-index`; ensure `CREATE EXTENSION vector`; `ollama pull nomic-embed-text`. |
| Digest / bot: Ollama errors | `ollama serve`, `OLLAMA_MODEL` pulled and spelled correctly. |
| Telegram PDF error | Fonts in `app/telegram/fonts/`, token + chat id, **`--telegram`** requires digest (no `--no-summarize`). |
| `DATABASE_URL` errors | URL reachable from the machine running Python; driver prefix matches `psycopg` expectations. |

#Test