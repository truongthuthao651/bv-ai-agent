# Trợ lý AI Bảo Việt Life

> **Local RAG assistant** for Bảo Việt Life employees — answers questions about company documents in **Vietnamese**, with **citations** and **LaTeX math**. Runs **fully offline** on one machine; no external API calls.

| | |
|---|---|
| **LLM** | Ollama — chat `qwen3:8b`, vision `qwen2.5vl:7b` |
| **Embeddings / rerank** | `bge-m3`, `bge-reranker-v2-m3` (local weights) |
| **Vector DB** | Qdrant — hybrid dense + sparse; embedded in-process (native mode) |
| **UI** | Single React app on port **8000** — `/`, `/chat`, `/admin` |

> ⚠️ **Security:** Never read or commit `data/real/` (confidential). Dev and tests use `data/synthetic/` only.

For architecture, development workflow, and project status, see **[TEAMMATE_GUIDE.md](TEAMMATE_GUIDE.md)**.

---

## Prerequisites

- **uv** — https://docs.astral.sh/uv/ (preferred; installs Python 3.12 when needed)
- **Python 3.11 or 3.12** — fallback only when uv is unavailable
- **Ollama** — https://ollama.com
- Internet only for **initial setup** (pip + model download); then fully offline

On Windows, run shell commands below in **Git Bash**. Node/npm is only needed on the **dev machine** to rebuild the frontend (`frontend/` → `app/static/dist/`).

---

## Quick start (native)

```bash
git clone <repo-url> bv-ai-agent && cd bv-ai-agent
cp .env.example .env          # edit CHAT_MODEL, SESSION_SECRET_KEY, ports if needed
bash scripts/setup_native.sh    # one-time: UV venv, models, optional frontend build
bash scripts/run_native.sh      # start Ollama + API
bash scripts/healthcheck.sh
bash scripts/seed_demo_accounts.sh   # demo admin: admin@baoviet.com / Admin123!
```

| URL | Who |
|-----|-----|
| http://localhost:8000/ | Public landing |
| http://localhost:8000/login | Sign in / sign up (`@baoviet.com`) |
| http://localhost:8000/chat | Any signed-in account |
| http://localhost:8000/admin | Admin role only |
| http://localhost:8000/health | Health check |

Stop: `bash scripts/stop_native.sh` · Logs: `logs/`

**Accounts:** admins via `scripts/seed_accounts.py`; employees self-register on `/login` ("Tạo tài khoản"). Role `employee` → `/chat` only; role `admin` → `/chat` + `/admin` (enforced server-side).

---

## Common commands

```bash
bash scripts/run_native.sh                  # start
bash scripts/stop_native.sh                 # stop
bash scripts/healthcheck.sh                 # smoke test
bash scripts/check.sh                       # ruff + pytest
bash scripts/ingest.sh data/synthetic       # index test corpus
bash scripts/seed_demo_accounts.sh          # create the local demo admin
```

---

## Configuration

All settings live in `.env` → `app/config/settings.py`. See `.env.example` for the full list.

| Variable | Notes |
|----------|-------|
| `CHAT_MODEL` | Default `qwen3:8b`; use `qwen3:4b` on weak machines |
| `LLM_THINKING` | Keep **`false`** for speed |
| `SESSION_SECRET_KEY` | Fixed random string so logins survive restarts |
| `QDRANT_LOCAL_PATH` | Embedded Qdrant storage (native mode) |
| `API_HOST` | Default `127.0.0.1`; set `0.0.0.0` for LAN access |
| `API_PUBLIC_BASE_URL` | Citation link base — set to server LAN IP when employees browse from other machines |
| `API_SHARED_SECRET` | Recommended when `API_HOST=0.0.0.0` |

**LAN:** If employees open `/chat` from other machines, set `API_HOST=0.0.0.0` and `API_PUBLIC_BASE_URL=http://<server-ip>:8000`. Also set `API_SHARED_SECRET` — see `.env.example`.

**Knowledge pack:** Public reference documents are downloaded manually into `data/knowledge_pack/` and indexed with `scripts/ingest_knowledge_pack.py` — the app never fetches URLs at runtime.

---

## English summary

A ChatGPT-like internal assistant for company documents (policies, procedures, forms, spreadsheets). One process, one port, role-based access. Deployment is `git clone` + `.env` + `scripts/setup_native.sh` + `scripts/run_native.sh` on a company laptop — no Docker, no Node on the deployment machine if `app/static/dist/` is already committed.

**Developer guide:** [TEAMMATE_GUIDE.md](TEAMMATE_GUIDE.md)
