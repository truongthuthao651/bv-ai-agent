# Phase 0 — System Map

Date: 2026-08-08. Prepared per `AUDIT_PROMPT.md`. Read-only phase — no edits made.

## 0.1 Tooling baseline (real output, not estimated)

| Check | Command | Result |
|---|---|---|
| Backend tests | `.venv/bin/python -m pytest -q` | **440 passed**, 0 failed, 0 skipped, 5.21s |
| Backend lint | `.venv/bin/ruff check app tests` | **All checks passed** |
| Backend format | `.venv/bin/ruff format --check app tests` | **79 files already formatted** |
| Frontend lint | `cd frontend && npm run lint` (oxlint) | **0 errors** — but see caveat below |
| `git status --short` | | **Dirty working tree**, ~15 files modified/deleted/renamed, uncommitted (Open WebUI removal + RBAC work — see §0.4) |
| `git log --oneline \| wc -l` | | 27 commits, `d47ec8e` (initial) → `78883a1` (latest, "Day 7 wrap-up") |

**Frontend lint caveat (real, from the tool's own stderr):**
```
warning: no-restricted-syntax dropped from generated oxlintrc — oxlint cannot
execute it. Hex/px/font-family and per-component prop-shape checks from the
design system are NOT enforced by `npm run lint`.
```
`npm run lint` passing 0-error is **not evidence of design-token compliance** — the one rule that would catch hardcoded hex/px/font-family literals is silently inert. Phase 3 must grep for these by hand rather than trust the lint output. This is itself a Phase 1 finding (a linter whose primary enforcement rule doesn't run, with no red flag when it doesn't).

## 0.2 Repo map

```
app/                    FastAPI backend (8,014 lines across api/generation/retrieval/ingestion)
  api/                  chat.py (629L), chat_ui.py, docview.py, health.py, ingest.py (471L),
                         login.py, metrics.py — HTTP layer
  generation/           generator.py (889L), prompts.py (600L), advisory.py, citations.py,
                         coverage_gate.py, history.py, verify.py — LLM orchestration
  retrieval/            retriever.py (115L), reranker.py, comparison.py, conversation_scope.py,
                         coverage.py, metric_guard.py, product_scope.py, query_expansion.py,
                         query_rewrite.py, spellcheck.py
  ingestion/             chunking.py, cleaning.py, enrichment.py, indexer.py, metric_hints.py,
                         router.py, parsers/ (docx, pdf, xlsx, image, ocr, formula_ocr, glossary,
                         figure_extract, markdown)
  config/settings.py     pydantic-settings, single source of truth for env config
  models/schemas.py      Pydantic request/response models
  auth.py, accounts.py   session cookie auth + SQLite account store (RBAC: admin/employee)
  main.py                app wiring, admin_session_gate middleware, static mounts
  query_timing.py         per-request JSONL logging → logs/query_timings.jsonl
  templates/login.html    plain Jinja page (not part of the Vite build)
  static/dist/            COMMITTED build output of frontend/ (index.html, admin/, chat/, app-assets/)
  static/fonts/, static/assets/, static/tokens/  vendored design-system assets, served directly

frontend/src/           Vite multi-page React app (3 entry points)
  landing-main.jsx  → dist/index.html        public landing page ("/")
  admin-main.jsx    → dist/admin/index.html  admin console ("/admin", admin role only)
  chat-main.jsx     → dist/chat/index.html   chat UI ("/chat", any signed-in account)
  admin/            AdminShell.jsx, OverviewView.jsx (462L), DocumentsView.jsx (322L),
                     UsersView.jsx (46L), api.js
  chat/             ChatScreen.jsx (152L), ChatMessage.jsx, Composer.jsx, EmptyState.jsx,
                     Sidebar.jsx, SourcePanel.jsx, markdown.jsx, api.js
  components/       Badge, Button, ChatBubble, ChatComposer, PromptSuggestion, KpiCard,
                     StatusPill, Table, Modal, Input, Card, ThemeToggle — vendored design system
  tokens/           colors.css, typography.css, spacing.css, radii-shadows.css, fonts.css, styles.css
  theme/useTheme.js  light/dark toggle
  showcase/          ComponentGallery.jsx, Showcase.jsx, ForcedThemeView.jsx — internal only

tests/             25 test files, 440 tests, all pass without live Ollama/Qdrant (see Phase 1 for how)
eval/              golden_set.jsonl (72 items), run_ragas.py, results/ (7 runs, 2026-08-05→08-07)
scripts/           run_native.sh, setup_native.sh, stop_native.sh, healthcheck.sh, seed_accounts.py,
                   ingest.sh, ingest_knowledge_pack.py, make_synthetic_data.py, chunk_stats.py,
                   check.sh, setup_models.sh, prompt_suggestions.json
docs/              TEAMMATE_GUIDE.md (STALE — flagged separately, references pre-removal Open WebUI
                   flow), audit/ (PRIOR audit cycle — see §0.4)
data/               synthetic/ (9 files, used for this audit), glossary/, accounts.db (SQLite);
                   data/real/ is OFF-LIMITS and was not read
```

## 0.3 Request-flow map (5-minute version)

```
Browser
  │
  ├─ GET /, /chat/*, /admin/*        (StaticFiles, html=True, app/main.py:221-225)
  │     └─ admin_session_gate middleware (app/main.py:135-190) runs FIRST for every request:
  │          1. Parses bv_admin_session cookie → request.state.account (auth.is_valid_session)
  │          2. /v1/* → require (API_SHARED_SECRET bearer) OR (valid account session)
  │          3. other paths → if auth is enabled and path is not public
  │             (auth.PUBLIC_PREFIXES) → require a session, redirect to /login if HTML request
  │          4. /admin/* specifically → require account.role == "admin", else redirect to /chat/
  │             (this is the RBAC enforcement point for PAGE access)
  │
  ├─ POST /login  (app/api/login.py) → app/accounts.py verifies PBKDF2 hash → sets session cookie
  │
  ├─ POST /v1/chat/completions  (app/api/chat.py, ~629L)
  │     query_expansion (glossary) → query_rewrite (LLM) → retriever.hybrid_search (dense+sparse,
  │     RRF fuse, top-20 each) → metric_guard filter → reranker.rerank (bge-reranker-v2-m3, top-5,
  │     collapses parent-child duplicates first) → coverage_gate → generator.stream_chat
  │     (Ollama, SSE) → citations.format_sources → StreamingResponse (text/event-stream)
  │     Advisory/general-knowledge modes branch inside prompts.py; comparison queries
  │     (≥2 products named) run retrieval+rerank PER PRODUCT (retrieval/comparison.py) and merge.
  │
  ├─ /ingest, /documents (app/api/ingest.py, 471L) — admin-only reads via
  │     Depends(auth.require_admin); parses (docling/pandoc/paddleocr per file type) → chunks
  │     (chunking.py, equation/table-safe) → enrichment.py (LLM formula descriptions, figure
  │     VLM captions) → indexer.py (bge-m3 dense+sparse → Qdrant, embedded/local mode)
  │
  └─ /metrics/summary (app/api/metrics.py) — admin-only, aggregates logs/query_timings.jsonl
```

**State**: chat history is in-memory per browser tab (no server-side persistence — confirmed
gap, see Phase 2); Qdrant runs embedded/local (no separate server process); accounts live in
`data/accounts.db` (SQLite, PBKDF2 hashes); ingested documents + figure assets under `data/`.

## 0.4 Context a fresh reviewer needs (not visible from code alone)

1. **This is the SECOND audit cycle.** `docs/audit/` holds a prior audit
   (`2026-08-05-audit.md`, `2026-08-05-metrics.md`) and a `roadmap.md` that was executed
   Day 1–7 (commits `6334093`..`78883a1`) — closing 5/6 tracked metrics (exception handling,
   observability logging, golden-set regression coverage for 6 historical failure classes,
   upload hardening, citation safety) and honestly leaving 3 golden-set items open
   (`q35`, `q52`, `q59` — root-caused, deliberately not over-fit). **Do not re-discover and
   re-report items that roadmap.md already tracked as fixed** — verify current state instead
   of assuming the old audit is stale, but cite it when it changes the finding's framing
   (e.g. "already fixed once" vs. "never addressed").
2. **The prior roadmap explicitly decided AGAINST a unified frontend** ("A unified single
   frontend replacing both Open WebUI and the admin page... Decided against... would cost
   weeks"). **That decision has since been reversed** — this session's own most recent work
   (uncommitted, see below) removed Open WebUI entirely, built a bespoke `/chat` UI, and
   unified everything onto one FastAPI process/port with RBAC. Phase 1/2/3 must audit the
   CURRENT single-frontend architecture, not the one `roadmap.md` describes.
3. **Working tree is currently dirty** (~15 files) with the Open WebUI removal + RBAC
   changeset: `app/main.py`, `app/auth.py`, `app/api/{login,ingest,metrics}.py`,
   `app/config/settings.py`, `app/templates/login.html`, `.env.example`, `docker-compose.yml`,
   `scripts/{healthcheck,ingest}.sh`, `CLAUDE.md`, `README.md`, plus deletion of
   `scripts/open_webui/{apply_branding.py,ingest_pipe.py,README.md}` and rename of
   `scripts/open_webui/prompt_suggestions.json` → `scripts/prompt_suggestions.json`. **This
   audit evaluates the working tree AS-IS (uncommitted included)** — that is the real,
   currently-running state (verified: `curl :8000/health` returns 200 with Ollama and Qdrant
   both up), not a hypothetical. Whether/when to commit is a separate decision for the user.
4. **`docs/TEAMMATE_GUIDE.md` is known-stale** (flagged earlier this session, not yet fixed):
   still documents the two-port Open-WebUI-based flow, `.venv-webui`, and
   `http://localhost:3000` as the chat URL. Phase 5 should treat this as a confirmed finding,
   not a new discovery to re-verify from scratch.
5. **Two demo accounts exist** for live testing (admin@baoviet.com / employee role at
   user@baoviet.com) — provisioned via `scripts/seed_accounts.py`. Do not print these
   credentials into any audit file (`.env`/secrets rule) or take screenshots that expose the
   password field content.
6. **`eval/results/`** holds 7 real RAGAS runs from 2026-08-05 through 2026-08-07 — Phase 1.3
   should read the last 3 (`run-20260807-090707.json`, `run-20260807-103630.json`,
   `run-20260807-142847.json`) for the actual trend rather than re-running RAGAS (slow, and
   `roadmap.md` §"Consistency/determinism" already documents non-determinism caveats worth
   inheriting rather than re-deriving).

## 0.5 Known-good areas (per prior audit + this session's own verification — don't waste time re-litigating unless something looks different now)

- Backend test suite: fast (5.2s), deterministic, all pass without live Ollama/Qdrant.
- `ruff check`/`ruff format`: clean.
- RBAC page-redirect (`/admin` → `/chat/` for non-admins) and endpoint-level guards
  (`Depends(auth.require_admin)` on `/documents` GET/PATCH/DELETE, `/metrics/summary`,
  `/accounts`) — added this session, verified via curl AND a real CDP-driven browser
  screenshot showing an employee redirected off `/admin/`. Phase 1.4 should still enumerate
  every route in a table per the prompt's instructions (verify, don't just trust this note).
- `/v1` auth gap (unauthenticated LAN access when `API_SHARED_SECRET` unset) — closed Day 1
  per roadmap.md, then the shared-secret-vs-session interaction bug (`/chat` 401s if the
  secret is later set) was found and fixed this session; both are covered by
  `tests/test_auth.py`.
