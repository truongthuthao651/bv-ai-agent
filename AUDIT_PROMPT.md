# Full-Project Evaluation Prompt

Paste everything below the line into Claude Code, from the repo root
(`/Users/haphan/Desktop/bv-ai-agent/bv-ai-agent`). Recommended: start in **plan
mode** or say "read-only, no edits" for Phase 1–5 so nothing changes until you
have read the report.

---

# ROLE & MISSION

You are a senior technical reviewer doing a **full product + engineering audit**
of this repository before it is handed to a real business unit. This is an
internal, fully-offline Vietnamese RAG assistant for a life-insurance firm:
FastAPI + Ollama + Qdrant backend, a single React (Vite) frontend serving three
surfaces (landing `/`, chat `/chat`, admin `/admin`), served from one process on
one port, with the built bundle committed to `app/static/dist/`.

Your mission is to produce a **brutally honest, evidence-backed evaluation** in
four domains — Dev/Engineering, Admin & User experience, Frontend/Visual design,
and Chatbot behaviour — plus cross-cutting concerns, and then a **prioritized,
sequenced improvement roadmap** that another agent (or you, later) can execute
without re-deriving context.

The end goals I care about most:
1. **The smoothest possible user experience** — nothing confusing, nothing that
   makes a user wait without feedback, nothing that loses their work.
2. **The most visually appealing, professional pages possible** — this is
   customer-facing inside a conservative insurance company; it must look like a
   product, not a demo.
3. **Code a team can maintain** after the original author is gone.

## Hard rules (non-negotiable)

- **NEVER read, list, open, or reference anything under `data/real/`.** It may
  contain confidential company documents. Use `data/synthetic/` only.
- **Never** print secrets from `.env` (it is committed locally but gitignored).
  If you need to discuss a setting, refer to the key name only, and cross-check
  `.env.example`.
- Do not put real document content, names, policy numbers, or amounts into any
  file you write.
- Phases 1–5 are **read-only**: no edits, no commits, no `npm run build`, no
  server restarts other than what Phase 4 explicitly needs. Ask before Phase 7.
- Read `CLAUDE.md` first and treat it as the spec. Where the code disagrees with
  `CLAUDE.md` or `README.md`, that mismatch is itself a finding.

## Evidence standard

Every finding must have:
- a **file:line** reference (or a screenshot path, or a command + its real output),
- the **actual observed behaviour**, not a guess,
- a **user-visible or maintenance consequence** — "why this matters",
- a **severity**: `P0 blocker` / `P1 major` / `P2 minor` / `P3 polish`,
- an **effort estimate**: S (<1h) / M (half-day) / L (multi-day).

Do not report anything you have not verified. If you suspect a problem but
cannot confirm it, put it in a separate "Unverified suspicions — needs a run"
list. Never inflate the report with generic best-practice advice that isn't
grounded in this codebase. **A short report of real problems beats a long report
of plausible ones.**

---

# PHASE 0 — Orient (do this first)

1. Read `CLAUDE.md`, `README.md`, `EVALUATION.md`, `REDESIGN_PROMPT.md`.
2. Map the repo: `app/` (api, retrieval, generation, ingestion, config, models),
   `frontend/src/` (landing, chat, admin, components, tokens, theme, showcase),
   `tests/`, `eval/`, `scripts/`, `docs/`.
3. Run and record the real state of the tooling:
   - `.venv/bin/python -m pytest -q` (full suite, note pass/fail/skip counts and runtime)
   - `.venv/bin/ruff check app tests` and `.venv/bin/ruff format --check app tests`
   - `cd frontend && npm run lint`
   - `git log --oneline | head -40`, `git status --short`
4. Write a **1-page system map** (request → auth → retrieval → rerank → generate
   → SSE → render) that a new engineer could read in 5 minutes. Include where
   state lives (in-memory chat history, embedded Qdrant, accounts file/DB).

Output Phase 0 as `audit/00-system-map.md`.

---

# PHASE 1 — Dev team: code quality, architecture, security

Produce `audit/01-engineering.md`.

## 1.1 Architecture & structure
- Are module boundaries real? Check for leakage: does `app/api/*` contain
  business logic that belongs in `retrieval/` or `generation/`? Note that
  `app/api/chat.py` (~630 lines) and `app/generation/generator.py` (~890 lines)
  are the two largest modules — assess whether they should be decomposed, and if
  so, propose the exact split (new file names, what moves where).
- Is there a clean seam between "RAG pipeline" and "web app"? Could the pipeline
  be tested/reused without FastAPI?
- Configuration: is `app/config/settings.py` the single source of truth, or are
  there hardcoded values, magic numbers, and stray `os.getenv` calls scattered
  around? List every one you find.
- Dependency hygiene: 4 requirements files — are they coherent, pinned,
  duplicated? Any unused or heavyweight deps that could be dropped?
- Frontend structure: is the vendored design system (`src/tokens/`,
  `src/components/`) actually used by `chat/`, `admin/`, and `landing/`, or do
  those screens re-implement buttons/cards/inputs locally? **Every locally
  re-implemented component is a finding** (the design system is supposed to flow
  in from outside the repo and never be hand-edited).

## 1.2 Code quality & maintainability
- Duplication: find genuinely repeated logic (not superficial similarity) across
  `app/` and `frontend/src/`. Name the top 5 by cost.
- Complexity hot spots: longest functions, deepest nesting, highest branch count.
  Give file:line and a concrete refactor.
- Error handling: are exceptions swallowed? Are user-facing errors distinguishable
  from bugs? Does every failure path produce something the user can act on?
- Naming/idiom consistency across Python and JS. Comment density: too little in
  the tricky retrieval/coverage-gate code, or noise elsewhere?
- Type coverage: how much of `app/` is typed? Are `app/models/schemas.py`
  Pydantic models used consistently at API boundaries, or are there raw dicts?
- Dead code: unused functions, unreachable branches, retired Open WebUI leftovers,
  stale scripts, stale `docs/`.

## 1.3 Tests & evaluation
- Coverage by module: which of the 24 test files actually exercise behaviour vs.
  assert trivia? Which modules have **no** meaningful tests?
- Are tests fast, deterministic, and independent of a running Ollama/Qdrant?
  Flag anything that silently skips when a service is down (a skipped test that
  looks green is worse than a failing one).
- Frontend: there appear to be **no JS tests at all** — confirm, and recommend a
  minimal high-value set (SSE stream parsing, markdown/KaTeX rendering, theme
  toggle, admin table state) rather than a coverage-chasing suite.
- `eval/`: is the golden set (`eval/golden_set.jsonl`) large and representative
  enough? Are the RAGAS runs in `eval/results/` trending up or down? Read the
  last 3 runs and report the actual numbers and the trend.
- Is there any CI? If not, propose the smallest useful pipeline that runs
  offline on a company machine.

## 1.4 Security & privacy (weight this heavily — insurance data)
Audit and report on:
- **Auth**: `app/auth.py`, `app/accounts.py`, `app/api/login.py`. Password
  hashing algorithm and parameters, session/cookie flags (`HttpOnly`, `Secure`,
  `SameSite`), session expiry, session fixation, logout, brute-force/rate limiting.
- **RBAC**: verify server-side enforcement on *every* mutating and admin-read
  endpoint (`ingest`, `docview`, `metrics`, user management) — not just the
  redirect in `admin_session_gate`. Enumerate each route and its guard in a table.
  Any route missing a guard is a **P0**.
- **Upload path** (`app/api/ingest.py`): file-type validation, size limits, path
  traversal in filenames, zip/XML bombs, where uploads land, what happens to a
  malicious PDF/DOCX/XLSX, whether parsing runs with any sandboxing.
- **Injection surfaces**: prompt injection from ingested documents into
  `app/generation/prompts.py` — can a document instruct the model? Are retrieved
  chunks clearly delimited/untrusted? Also check for command injection in
  `scripts/*.sh` and any `subprocess` calls (pandoc, ollama, OCR).
- **Output safety**: does the chat renderer sanitize model output?
  `frontend/src/chat/markdown.jsx` — check for `dangerouslySetInnerHTML`, raw
  HTML passthrough, KaTeX `trust` options, and link handling (XSS via a citation
  or a document title).
- **Data leakage**: logs under `logs/` — do they contain question text, document
  content, or PII? Check `app/query_timing.py` and any logging config. Confirm
  `.gitignore` actually covers `data/`, `.env`, `models/`, `qdrant_storage/`, and
  that nothing sensitive is already tracked (`git ls-files | grep -Ei 'env|data/'`).
- **Headers & transport**: CORS config, CSP, `X-Content-Type-Options`, and what
  happens when this is served over plain HTTP on a LAN.
- **Dependency risk**: any pinned package with a known-bad version; note that the
  deployment machine is offline so patching is manual — flag anything that would
  be painful to update.

Deliver a **security findings table** sorted by severity, plus a short
"if you fix only three things, fix these" list.

## 1.5 Ops & deployment
- Docker-free native deploy (`scripts/run_native.sh`, `setup_native.sh`,
  `stop_native.sh`): is it idempotent? What happens on a half-failed setup?
- Is the committed `app/static/dist/` bundle **in sync** with `frontend/src`?
  Verify — a stale bundle means the deployed UI silently differs from the code.
  Propose a guard (build hash check, pre-commit, or a `make check`).
- Backup/restore story for `qdrant_storage/` and accounts. Upgrade/rollback path.
- Startup failure modes: Ollama not running, model not pulled, corrupt index,
  disk full. Does the app fail loudly and legibly, or hang?
- Observability: what can an admin actually see when something is slow or wrong?

---

# PHASE 2 — Admin & Users: features, logic, professionalism

Produce `audit/02-product.md`.

Work through **every screen and every interactive element**, as three personas:

- **Nhân viên (employee)** — non-technical, Vietnamese-first, wants an answer fast
  and needs to trust the citation.
- **Admin** — uploads and curates documents, watches metrics, manages accounts.
- **First-time user** — has never seen the tool, got a link in an email.

## 2.1 Journey walkthroughs
For each journey, list every step, every click, and every moment of uncertainty:
1. Land on `/` → understand what this is → log in → ask a first question.
2. Ask a follow-up → check a citation → open the source document → come back.
3. Get a bad/refused answer (coverage gate) → understand why → recover.
4. Admin: upload a document → watch it process → verify it's searchable →
   edit metadata → delete it → confirm it's gone from answers.
5. Admin: read the metrics/overview and answer "is the system healthy today?"
6. Account lifecycle: provisioning (`scripts/seed_accounts.py`), first login,
   password change, forgotten password, deactivation. **What is missing here is
   probably the biggest product gap — say so plainly.**

## 2.2 Feature completeness
Explicitly assess these known gaps and rank them by user pain:
- **No conversation persistence** — history is in-memory per page load. What
  breaks for a user who refreshes? Recommend the smallest change that fixes it.
- **No self-service anything**: no signup (fine), but also no password reset, no
  profile page, no user settings. What is the minimum viable profile surface?
- **`UsersView.jsx` is 46 lines** vs `OverviewView.jsx` at 462 — is user
  management a real feature or a stub? Report what an admin actually can and
  cannot do.
- Search/filter/sort/pagination in the documents table at realistic scale
  (what happens at 50, 500, 5000 documents?).
- Bulk operations, undo, and confirmation for destructive actions.
- Export (answers, metrics, document lists) — does anyone need it?
- Feedback loop: can a user flag a wrong answer? If not, that's how quality
  never improves — assess.

## 2.3 Interface logic & consistency
- Are terms consistent across all three surfaces and both languages? Build a
  **terminology table** (Vietnamese term → English → where used) and flag every
  inconsistency. Mixed VN/EN in the same view is a professionalism finding.
- Empty states, loading states, error states, success confirmations — for
  **every** async action. List each one that is missing or ugly.
- Destructive-action safety: delete document, delete user. Confirmation copy,
  reversibility.
- Form validation: inline vs. on-submit, error copy quality, keyboard behaviour
  (Enter to submit, Esc to close modal), focus management after modal close.
- Does the admin console explain *itself*? Would a new admin know what
  "coverage gate", "rerank", "chunk" mean, or do labels leak engineering jargon
  into a business user's screen? **Rewrite every jargon label you find.**

## 2.4 Professionalism check
Score the product as if a Bảo Việt Life executive opened it cold:
- Does it look finished? Any placeholder text, lorem ipsum, TODO in the UI,
  console noise, broken images, default browser styling?
- Vietnamese copy quality: tone, formality, diacritics, truncation. Flag anything
  machine-translated-sounding.
- Branding: is the logo used correctly and consistently? Favicon? Page titles?
  Loading/tab title while streaming?

---

# PHASE 3 — Frontend: visual design, theming, components

Produce `audit/03-frontend.md`.

**This phase must be done with the app actually running and screenshots taken.**
Do not evaluate the UI by reading JSX alone.

## 3.1 Setup
- Start the app (`scripts/run_native.sh` or the documented dev flow), then use
  the browser tools to visit `/`, `/chat`, `/admin`, and the component showcase
  (`frontend/src/showcase/`).
- Capture screenshots into `audit/screenshots/` at **three viewports**
  (mobile 375, tablet 768, desktop 1440) × **both themes** (light, dark) for
  every screen and every major state (empty, loading, streaming, error, full).
  Name them `{screen}-{viewport}-{theme}-{state}.png`.
- Compare against the existing `../screenshots/` in the parent design-system
  folder and `REDESIGN_PROMPT.md` intent — has the redesign actually landed?

## 3.2 Design tokens & consistency
- Audit `src/tokens/` (spacing, typography, color, radii) against actual usage.
  **Find every hardcoded value** in JSX/CSS that should be a token: raw hex
  colors, `px` spacing off the scale, one-off font sizes, ad-hoc border radii.
  Produce a table: file:line → hardcoded value → correct token.
- Spacing rhythm: is there a consistent scale (4/8pt) or drift? Check vertical
  rhythm between sections, card padding, form field spacing, list density.
- Type scale: how many distinct font sizes/weights are actually rendered? If it's
  more than the token scale defines, that's the finding. Check line-height and
  measure (line length) for Vietnamese text, which runs longer than English.
- Alignment and optical balance: gutters, grid consistency, misaligned icon/text
  baselines.

## 3.3 Color & theming
- Verify **both** light and dark mode on every screen. Look specifically for:
  low-contrast text, invisible borders, "dark mode afterthought" surfaces that
  are pure `#000` or unadjusted brand colors, charts/graphs that only work in one
  theme, focus rings that vanish, and images/logos with baked-in white backgrounds.
- Check `src/theme/useTheme.js` and `ThemeToggle.jsx`: does the choice persist?
  Does it respect `prefers-color-scheme` on first visit? Is there a
  flash-of-wrong-theme on load? Does it apply to *all three* surfaces?
- **Accessibility contrast**: compute actual WCAG ratios for body text, muted
  text, placeholder text, disabled states, badges, and buttons in both themes.
  Report every pair below 4.5:1 (3:1 for large text) with the measured number.
- Semantic color: are success/warning/error/info used consistently and
  distinguishable for color-blind users (not color-only signals)?

## 3.4 Components
Go component by component in `src/components/` (Button, Badge, Input, Card,
Table, Modal, KpiCard, StatusPill, ChatBubble, ChatComposer, PromptSuggestion,
ThemeToggle) and report for each:
- All states implemented? (default / hover / active / focus-visible / disabled /
  loading / error) — flag missing states, especially `:focus-visible`.
- Consistent sizing and variants, or ad-hoc props?
- Is it actually used everywhere it should be, or bypassed?
- Keyboard + screen-reader behaviour: modal focus trap and Esc, table header
  semantics, button vs. div, `aria-label` on icon-only buttons, live regions for
  streaming text.

## 3.5 Tables, graphs & data display
- `Table.jsx` + `DocumentsView.jsx`: sticky headers, column alignment (numbers
  right-aligned, monospace for IDs), truncation vs. wrapping, row hover, sort
  affordance, zebra vs. borders, responsive behaviour on mobile, and what an
  empty/loading/error table looks like.
- Charts in `OverviewView.jsx`: are they real charts or numbers in boxes?
  Evaluate axis labels, units, gridlines, tooltips, legend, color palette in
  both themes, and whether the chart answers a question an admin actually has.
  If charts are missing where they'd help, **propose specific ones** (latency
  distribution over time, queries per day, top documents cited, coverage-gate
  refusal rate, ingestion success rate).
- KPI cards: is the number the hero? Is there a comparison/trend, or a bare
  number with no context?

## 3.6 Motion, polish & performance
- Transitions: any jank, layout shift (CLS) when messages stream in, or abrupt
  state changes that need a transition? Any animation that's too slow/too bouncy
  for a corporate tool? Check `prefers-reduced-motion`.
- Bundle: measure the built `app/static/dist/` size, largest chunks, whether
  KaTeX/fonts are lazy-loaded, font loading strategy (FOUT/FOIT), and cold-load
  time on the landing page.
- Console: zero errors and zero warnings on every screen — check and report what's there.
- Responsive: does the chat sidebar collapse sensibly? Is the admin table usable
  on a laptop at 1280? Is anything horizontally scrolling the whole page?

For every visual finding, give a **concrete fix** (the token, the value, the CSS),
not "improve spacing".

---

# PHASE 4 — Chatbot: streaming, latency, chat UX

Produce `audit/04-chatbot.md`.

**This phase requires running real queries against the running stack.** Use
questions grounded in `data/synthetic/` and the `eval/golden_set.jsonl` set.

## 4.1 Streaming mechanics
- Trace the full path: `frontend/src/chat/api.js` (`resp.body.getReader()`) ←
  SSE ← `app/api/chat.py:142/575/600` (`StreamingResponse`,
  `text/event-stream`) ← `app/generation/generator.py`.
- Verify: correct SSE framing, no buffering by any layer, chunk boundaries not
  splitting UTF-8 Vietnamese characters or LaTeX delimiters mid-token, and
  incremental KaTeX rendering that doesn't flash broken math while `$$` is
  incomplete.
- **Cancellation**: can the user stop a generation? Does stopping actually abort
  the server-side work, or does it keep burning the GPU? Does navigating away or
  refreshing mid-stream leak a request? Test it.
- **Failure mid-stream**: kill Ollama during a response. What does the user see?
  Partial answer with no explanation is a P1.
- Reconnect/retry behaviour, timeouts, and what happens on a slow first token.
- Concurrency: two tabs, two users at once — does it queue, degrade, or break?

## 4.2 Timing & speed (measure, don't estimate)
Run at least **10 representative queries** (short factual, long multi-hop,
math-heavy, out-of-scope, follow-up) and record a table of:
- time to first token (TTFT),
- total wall time,
- tokens/sec,
- retrieval time vs. rerank time vs. generation time
  (use `app/query_timing.py` — verify what it actually measures and whether
  `first_token_ms` is populated on all paths).

Then:
- Identify the dominant cost. Is the reranker or query expansion worth its
  latency? Quantify: what would P50/P95 look like without each stage, and does
  answer quality actually drop (check against the golden set)?
- Is timing surfaced to the *user* (a subtle "thinking…" with elapsed time) and
  to the *admin* (metrics)? Recommend what should be visible and what shouldn't —
  a visible timer can make a slow system feel slower.
- Perceived speed: is there an immediate acknowledgement on send? Does the input
  clear/disable correctly? Is there a skeleton or a spinner during retrieval,
  before the first token arrives? **The gap between send and first token is the
  single biggest perceived-quality lever — measure it and fix it.**

## 4.3 Chat interface quality
- Composer (`Composer.jsx`): Enter to send / Shift+Enter newline, autogrow,
  max height, paste behaviour, disabled state while streaming, character or
  token limits, and mobile keyboard behaviour.
- Message list (`ChatScreen.jsx`, `ChatMessage.jsx`): autoscroll that doesn't
  fight the user when they scroll up, a "jump to latest" affordance, message
  grouping, timestamps, copy button, regenerate, edit-and-resend.
- Rendering (`markdown.jsx`): code blocks, tables, lists, links, and KaTeX —
  test a long inline formula, a display formula, and a table with Vietnamese
  headers. Check line-height and font pairing for math inside prose.
- Citations (`SourcePanel.jsx`, `app/generation/citations.py`): are they precise,
  clickable, and verifiable? Can the user see the exact chunk that grounded the
  claim? Does the panel work on mobile? Are citation numbers stable while streaming?
- Sidebar (`Sidebar.jsx`) and `EmptyState.jsx`: do the prompt suggestions
  (`scripts/prompt_suggestions.json`) reflect what the corpus can actually
  answer? Test each suggestion — **a suggested prompt that gets refused is a
  serious trust bug.**
- Refusals and the coverage gate (`app/retrieval/coverage.py`,
  `app/generation/coverage_gate.py`, `verify.py`): when the system declines, is
  the message honest, specific, and actionable in Vietnamese? Does it suggest a
  next step? Test 5 deliberately out-of-scope questions and quote the responses.
- Conversation scope / follow-ups (`app/retrieval/conversation_scope.py`,
  `query_rewrite.py`): test a 4-turn conversation with pronouns and ellipsis
  ("còn cái kia thì sao?"). Report where it loses the thread.

## 4.4 Answer quality spot-check
Run 10 golden-set questions and grade each: grounded / partially grounded /
hallucinated / wrongly refused. Compare to the latest `eval/results/` run and
say whether the automated numbers match what you observe. Note any systematic
failure mode (e.g. numbers from tables, formula transcription, product-name
disambiguation).

---

# PHASE 5 — Cross-cutting

Produce `audit/05-crosscutting.md`.

- **Accessibility (WCAG 2.1 AA)**: keyboard-only run of every flow, focus order,
  skip links, landmarks, headings hierarchy, form labels, live regions for
  streaming, contrast (from Phase 3), zoom to 200%. This is an internal corporate
  tool — accessibility is likely a procurement requirement, treat it as such.
- **Internationalization**: hardcoded Vietnamese strings scattered in JSX vs. a
  strings module. Is an English mode ever needed? Number/date/currency formatting
  for `vi-VN`.
- **Documentation**: is `README.md` accurate enough that the IT person who
  installs this can succeed without you? Is `CLAUDE.md` still true? Is there an
  admin user guide in Vietnamese? A troubleshooting page? **Test the install
  instructions by reading them as someone who has never seen the repo.**
- **Resilience**: disk full, corrupt Qdrant index, Ollama OOM, 200MB PDF upload,
  50 concurrent users. Which of these has a graceful path?
- **Privacy/compliance posture**: what is logged, retained, and for how long;
  what an auditor would ask for.

---

# PHASE 6 — Report & roadmap (the deliverable)

Produce `audit/REPORT.md` — the single document I will actually read.

## 6.1 Scorecard
Score each domain **0–10 with a one-line justification and the 2 findings that
cost it the most points**. Be a harsh grader; a 7 should mean "genuinely good".

| Domain | Score | Biggest drag |
|---|---|---|
| Architecture & structure | | |
| Code quality & maintainability | | |
| Testing & evaluation | | |
| Security & privacy | | |
| Ops & deployment | | |
| Admin experience | | |
| End-user experience | | |
| Visual design & consistency | | |
| Accessibility | | |
| Chatbot streaming & latency | | |
| Chat interface quality | | |
| Answer quality & trust | | |
| Documentation | | |

## 6.2 Executive summary
Ten sentences maximum. What is genuinely good, what is the single biggest risk,
and what would I regret shipping.

## 6.3 Findings register
One table, all findings, sorted by severity then effort:
`ID | Domain | Severity | Effort | File:line | Finding | User/maintenance impact | Fix`

## 6.4 Roadmap
Sequenced, dependency-aware, and honest about effort:

- **Wave 0 — Ship blockers (do before anyone else sees this).** Security P0s,
  data-loss risks, anything broken on a main flow.
- **Wave 1 — Smoothness (highest UX return per hour).** Perceived latency, loading
  and error states, cancellation, conversation persistence, autoscroll, focus
  management. For each item state the *felt* difference.
- **Wave 2 — Visual polish and design-system compliance.** Token cleanup, dark
  mode fixes, contrast, table and chart redesign, component state completion.
  Include a short **before → after spec** for the three worst-looking screens.
- **Wave 3 — Product gaps.** Profiles, account lifecycle, feedback loop, admin
  user management, exports.
- **Wave 4 — Engineering health.** Decomposition of the two large modules, test
  gaps, frontend tests, CI, bundle-sync guard, docs.
- **Wave 5 — Nice to have.**

For each wave: the ordered task list, the files each task touches, an
acceptance criterion per task ("done when…"), and a rough total effort. Mark any
task that is safe to hand to a fresh agent with `[parallel-safe]`.

## 6.5 Quick wins
A separate list of everything that is **S effort and ≥P2 impact** — the "one
afternoon makes this feel like a different product" list. Aim for 10–20 items.

## 6.6 Unverified suspicions
Things worth checking that you could not confirm, with the command or test that
would confirm each.

---

# PHASE 7 — Implementation (only after I approve)

**Stop after Phase 6 and wait for my go-ahead.** Do not edit code before that.

When I approve, execute wave by wave:
- One logical commit per task, message explaining the *why*.
- Run `pytest`, `ruff`, and `npm run lint` before each commit; rebuild the
  frontend and commit `app/static/dist/` whenever `frontend/src` changes.
- Re-screenshot any screen you touch and put before/after pairs in
  `audit/screenshots/after/`.
- Never touch `data/real/`. Never commit `.env`.
- Keep a running `audit/CHANGELOG.md`: what changed, what it fixed, what it
  didn't, and anything you deliberately skipped with the reason.
- If a fix turns out to be bigger than estimated, stop and tell me rather than
  silently expanding scope.

# Working style

- Read before you conclude. Run before you claim. Screenshot before you judge UI.
- Prefer the smallest change that fixes the root cause over a rewrite.
- Where you recommend a redesign, show the concrete target (values, tokens,
  layout), not adjectives.
- Tell me when something is already good — I need to know what not to touch.
