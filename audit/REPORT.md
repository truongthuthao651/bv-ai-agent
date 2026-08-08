# bv-ai-agent — Full Product + Engineering Audit

Date: 2026-08-08. Scope, method, and hard rules per `AUDIT_PROMPT.md`. This is the single
document meant to be read end to end; `00-system-map.md` through `05-crosscutting.md` hold the
full evidence trail (file:line citations, screenshots, live query transcripts) behind every claim
made here. `data/real/` was never opened. No secrets were printed. Phases 0-6 were executed
read-only, as instructed; **Phase 7 (implementation) has not started** and awaits explicit
go-ahead.

A note on scope that shapes every finding below: this audit ran against the **working tree as it
sits on disk right now**, which includes an uncommitted, in-progress changeset that fully removes
Open WebUI and moves the app to a single-port, RBAC-gated, bespoke `/chat` + `/admin` + `/`
architecture. That changeset is the real, currently-running system (`/health` returns 200, all
440 tests pass against it) — so this audit evaluates *that* system, not the last commit.

---

## 6.1 Scorecard

| Domain | Score | Biggest drag |
|---|---|---|
| Architecture & structure | 7/10 | RAG/web-app seam is logically clean, but `app/api/chat.py` physically holds 280 lines of pipeline orchestration; `/chat`'s 5 screen files bypass the design system's `Button` component entirely |
| Code quality & maintainability | 7/10 | Genuinely disciplined error handling and config hygiene; the one real hotspot (`_stream_chat`, 85 lines) is dense but not duplicated |
| Testing & evaluation | 6/10 | 440 fast, real (non-trivial) backend tests — but **zero** frontend tests, and the single most security-relevant behavior found this audit (unauthenticated document routes) has no regression test |
| Security & privacy | 5/10 | RBAC on mutating/admin-read routes is solid and re-verified live, but `GET /documents/{id}/{file,view}` are reachable with **zero authentication** on a LAN-open-by-default install — the one finding in this whole audit that lets a stranger read real policy content |
| Ops & deployment | 5/10 | Deploy scripts are genuinely idempotent and defensive — undercut by the committed frontend bundle currently being **untracked in git**, meaning a fresh clone serves no UI at all, with no automated guard that would have caught it |
| Admin experience | 6/10 | The Overview dashboard is a real strength; account lifecycle is 100% a server-shell operation (no reset, no deactivation) and the admin console has **zero responsive layout** — unusable on a tablet, let alone a phone |
| End-user (chat) experience | 6/10 | Grounded, cited, honest-refusal answers work correctly in every live test run — undercut by no cancellation, no persistence across refresh, and 8-50 second waits with no "thinking" indicator at all |
| Visual design & consistency | 6/10 | Small, disciplined token system, clean bundle (1.7MB), zero console errors — undercut by a landing page that silently never themes and light-mode muted text that fails WCAG contrast by a wide margin (2.58:1) |
| Accessibility | 5/10 | Focus rings are never suppressed anywhere (a real, easy-to-miss thing done right) and landmarks/labels are mostly correct — but there is no live region for 8-50 second streaming answers, meaning a screen-reader user gets total silence for the entire wait |
| Chatbot streaming & latency | 5/10 | SSE framing and math-delimiter safety are both correct and confirmed live — but median latency across two independent measurements sits at 12-40 seconds with no cancellation and no perceived-wait mitigation |
| Chat interface quality | 6/10 | Citations are precise and genuinely clickable; the friendliest, most actionable part of the UI (the refusal recovery message) is dead code due to a one-line string-comparison bug |
| Answer quality & trust | 7/10 | Every grounded live answer in this audit's 10-query sample was correctly cited and honest; the one real trust gap is a general-knowledge fallback that will write an off-topic poem rather than staying in an insurance/actuarial lane |
| Documentation | 5/10 | `README.md`/`CLAUDE.md` are accurate as of this session's own edits — `docs/TEAMMATE_GUIDE.md` (840 lines) is the most out-of-date document in the repo, actively describing a retired architecture in at least 12 places |

## 6.2 Executive summary

This is a substantially more capable and better-engineered system than its scorecard alone
suggests — the RAG pipeline, RBAC enforcement, error handling, and Vietnamese copy quality are
all genuinely good, and every live test run in this audit (10 chat queries, RBAC checks from both
roles, upload/edit/delete flows) behaved correctly and honestly. The single biggest risk is that
`GET /documents/{id}/file` and `/view` have **no authentication at all** on a LAN-open-by-default
install, letting anyone who can guess a filename read real policy content with zero credentials —
this is the one finding here that would actually hurt someone if shipped as-is. The second-biggest
risk is operational, not technical: the committed frontend bundle is currently **untracked in
git**, so a fresh clone of this exact repository right now serves no user interface whatsoever,
and nothing would have caught that automatically. What I would most regret shipping, beyond those
two, is the combination of an 8-50 second wait with **zero cancellation and zero "thinking"
indicator** — every one of the three independent audit passes that touched the chat UI flagged
this same gap unprompted, which is a strong signal it is the single highest-value UX fix
available. The admin console's complete absence of responsive layout (unusable below ~900px) is
the biggest visual-design gap. None of this requires a rewrite: every P0/P1 finding in this report
has a same-day fix.

## 6.3 Findings register

Sorted by severity, then effort. IDs prefixed by originating phase doc; several findings were
independently rediscovered by 2-3 phases run in parallel — those are marked "×N" and cite every
source, which is itself a confidence signal, not double-counting.

| ID | Domain | Sev | Effort | File:line | Finding | Impact | Fix |
|---|---|---|---|---|---|---|---|
| SEC-A | Security | **P1** | S | `app/api/ingest.py:306,342`; `app/auth.py:79-84,154-159` | `/documents/{id}/file` and `/view` have no session check at all | Anyone who guesses a filename reads full document content with zero credentials, on the default LAN-open config | Require *any* valid session (not admin-only); add a regression test |
| OPS-A | Ops | **P1** | S | `app/static/dist/` (git status: `??`) | Committed frontend bundle is currently untracked | Fresh clone/stash serves no UI at all on any of the 3 surfaces | `git add app/static/dist/`; add a build-sync guard to `scripts/check.sh` so this can't silently recur |
| CHAT-1 | Chat UX | **P1** | S | `frontend/src/chat/api.js:26-51`; `ChatScreen.jsx` (no stop control anywhere) | No cancellation — once sent, a query cannot be stopped | Given 8-50s waits, a wrong/regretted question is a forced one-way wait every time | `AbortController` in `askStreaming` + a visible "Dừng" button; add `request.is_disconnected()` check server-side |
| WAIT-1 ×3 | Chat/Product UX | **P1**→ | S | `ChatScreen.jsx:52` / `ChatMessage.jsx:129`; independently flagged by Phase 2 (P2-J1), Phase 4 §4.2, and this report's own synthesis | Zero loading affordance during the 8-50s gap before first token — blank bubble, only the send button greys out | The prompt's own words: "the single biggest perceived-quality lever" — three independent passes agreed unprompted | Render a "Đang tìm trong tài liệu…" status line (or animated dots) in the empty bubble until first delta |
| F3-4 | Frontend | **P1** | M | `frontend/src/admin/AdminShell.jsx:156`; `OverviewView.jsx:378` | Admin console has zero responsive layout — rail never collapses, 5-col KPI grid never reflows | Admin is unusable at ≤900px (confirmed by screenshot: KPI labels truncate to "Số...", "Tài...") — the exact `useIsMobile()` pattern already exists and works in `chat/ChatScreen.jsx:10-19` | Port the chat sidebar's collapse pattern to `AdminShell`; make the KPI grid `auto-fit` |
| F3-3 | Frontend/A11y | **P1** | S | `frontend/src/tokens/colors.css:12` | `--text-muted` (light theme) is 2.58:1 against `--bg` — fails WCAG AA (4.5:1) | Every muted caption/placeholder is hard to read in light mode specifically (dark mode passes at 5.54:1) | Darken to ~`#5F7488` (computed ≈4.6:1); re-check against `--surface` too |
| F3-1 | Frontend | **P1** | S | `frontend/src/landing/LandingScreen.jsx:15-17,43,67` | Landing page never themes — 4 hardcoded hex values bypass the token system entirely | Only screen where dark mode silently does nothing; no toggle shown either, so it reads as a gap not a choice | Either document as deliberate (one comment) or swap to `var(--text-on-accent)`/`var(--brand-ink)` |
| P2-J6 | Product | **P1** | M | `app/api/login.py` (83 lines, full); `app/accounts.py` (144 lines, full) | No self-service password reset/change, no forced first-login change, no deactivation | Entire account lifecycle is a server-shell operation — doesn't scale past a small pilot, real offboarding risk | Minimum viable: one `/me` page, `POST /change-password` (S/M once `update_password` exists in `accounts.py`) |
| P2-F1 | Product | **P1** | S-M | `frontend/src/chat/ChatScreen.jsx:25` | No conversation persistence — refresh/tab-close loses the whole thread | Breaks the ordinary use pattern of "read a long answer, come back to it" | Persist `messages` to `sessionStorage`, rehydrate on mount — no backend change needed |
| P2-F2 | Product | **P1** | M | `frontend/src/chat/ChatMessage.jsx:64-86` | No feedback loop — no thumbs-down, no "báo lỗi" | No signal path from "assistant was wrong" back to whoever curates the corpus; quality can only rot silently | Thumbs-down icon → log-only endpoint (JSONL, mirrors `query_timing.py`'s pattern) |
| REFUSAL-UI ×3 | Chat UX | P2 | S | `frontend/src/chat/ChatMessage.jsx:5,116`; `app/query_timing.py:79-86`; independently confirmed by Phase 2 (P2-J3), Phase 4 §4.3, and this report's own live queries #3/#7 | `isRefusal` exact-string check is always false because the timing footer is always appended — the friendlier recovery message is dead code | User sees a raw refusal sentence + timing footer, no rephrase suggestion, in 100% of refusals | One line: compare with the footer stripped, or `.startsWith(REFUSAL_TEXT)` |
| MODE-1 | Chat/Admin | P2 | S | `app/api/chat.py` (mode set from *route taken*, not outcome); confirmed live via `logs/query_timings.jsonl` (2 entries `mode:"hybrid"` whose actual text was the literal refusal sentence) | `mode_breakdown`/refusal-rate undercounts: the hybrid path can independently emit the refusal sentence without `mode` ever becoming `"refusal"` | Admin's "Tỷ lệ không tìm thấy" KPI is not trustworthy as-is — silently misses hybrid-path refusals | After generation, if `_is_refusal(answer)` (already exists, `generator.py:284-286`) is true, log `mode="refusal"` regardless of route taken |
| CHAT-2 | Chat UX | P2 | M | `app/generation/generator.py:396,586,847` vs `:463-469` | `first_token_ms` populated on only 1 of 4 logging call-sites — coverage-gate answers (highest-stakes category) have no TTFT data at all | Admin's p50/p95 latency KPI silently mixes TTFT and total-time depending on which path answered | Thread `first_token_s` through the other 3 call sites |
| P2-C1 | Product | P2 | S | `frontend/src/admin/DocumentsView.jsx:234,240` | Delete confirmation uses native `window.confirm`/`alert`, not the app's own themed `Modal` | Breaks theme/brand consistency, freezes the tab, jarring vs. every other confirmation | Swap to `Modal` + existing `Button variant="danger"` — drop-in |
| P2-C2 | Product | P2 | S | `frontend/src/admin/DocumentsView.jsx:122-211` | Enter doesn't submit the Edit-document form (works everywhere else in the app) | Inconsistent, easy to miss for a keyboard-first admin | One `onKeyDown` handler, same IME-safe pattern as `Composer.jsx` |
| P2-C3 | Product/A11y | P2 | S | `frontend/src/components/feedback/Modal.jsx` | No Esc-to-close on the shared `Modal` | Standard modal expectation missing app-wide (one component, benefits every modal) | `useEffect` + `keydown` listener while open |
| P2-C4 | Product/A11y | P2 | M | `frontend/src/components/feedback/Modal.jsx` | No focus trap / no focus return after close | Keyboard-only admin loses their place after every edit | Real focus-trap implementation (Tab-cycling + return-focus) |
| P2-J2 | Product | P2 | S | `frontend/src/chat/ChatMessage.jsx:7-62` | Citation chips render for all 5 retrieved sources even when the prose only cites 1-2 | User opens "Nguồn 3" expecting it grounds a claim it never actually supported | Only render chips for `n`s that actually appear in the answer body |
| P2-F3 | Product | P2 | M | `frontend/src/components/data/Table.jsx`; `app/api/ingest.py:264-269` | No search/filter/sort/pagination in the documents table, no server-side pagination either | Fine at 50 docs, real problem at 500+, both UI and backend break at 5000 | Client-side filter `Input` first (S), server pagination once corpus grows (defer) |
| P2-T1 | Product | P2 | S | `frontend/src/admin/UsersView.jsx:24` | Copy says accounts are "for the admin page" when most are chat-only employee accounts | Misleading leftover copy from before the RBAC split | One string change |
| P2-T2 | Product | P2 | S | `DocumentsView.jsx:288,443`; `OverviewView.jsx:5` | `doc_type` shown as raw English enum (`"policy"`, `"other"`) in tables/charts while its own input dropdown is bilingual | Mixed VN/EN in the same view, the exact pattern the prompt asks to flag | Extract `EDIT_DOC_TYPE_OPTIONS` into a shared label map (mirrors `MODE_LABELS`) |
| ENG-1 | Architecture | P2 | M | `frontend/src/chat/{ChatScreen,ChatMessage,Composer,EmptyState,SourcePanel}.jsx` | `/chat`'s 5 screens hand-roll `<button>` instead of importing `Button` — `/admin` does it correctly | A design-system update (focus ring, hover timing, an a11y fix) silently never reaches the chat UI's send button | Swap raw buttons for `Button`/icon-button variants once an icon-only variant with `aria-label` exists |
| CHAT-3 | Chat UX | P2 | S | `frontend/src/chat/Composer.jsx` (fixed `rows={2}`, `resize:"none"`) | No autogrow — long multi-line questions scroll inside a cramped 2-row box | Small but real friction on the single most-used control in the product | `scrollHeight`-driven height adjustment |
| SEC-B | Security | P2 | S | `app/config/settings.py:37,64` | `api_host=0.0.0.0` + empty `api_shared_secret` are the *defaults*, not opt-ins; compounds with SEC-A | Unauthenticated LAN caller can hit `/v1/chat/completions` and (via SEC-A) read documents, out of the box | `.env.example`: require secret before `API_HOST=0.0.0.0` is honored |
| SEC-C | Security | P2 | M | `app/api/login.py:45-51` | Session cookie has no `Secure` flag; app has no TLS story anywhere | Session token is LAN-sniffable in cleartext | Document a reverse-proxy-TLS deployment pattern, or explicitly accept plaintext-LAN as the threat model |
| SEC-D | Security | P2 | M | `app/api/login.py:31-54` | No brute-force/rate-limit protection on `POST /login` | Nothing stops a scripted credential-stuffing loop | Simple per-email/IP attempt counter with backoff |
| SEC-E | Security | P2 | S | `app/generation/prompts.py` (rule blocks) | No "context is data, not instructions" rule for the model | Defense-in-depth gap if a compromised/adversarial document is ever ingested | One added sentence to the existing rule blocks |
| SEC-F | Security | P2 | S | `frontend/src/chat/markdown.jsx:65-86` | Free-text `[text](url)` links in model prose have no scheme allowlist | `javascript:`-href XSS possible if the model is made to emit one (via SEC-E) | Allowlist `http:`/`https:`/`/documents/...` in `renderInlineRun` |
| F5-2 | A11y | P2 | M | `frontend/src/chat/ChatScreen.jsx`, `ChatMessage.jsx` (no `aria-live` anywhere) | No live region for streaming text | Screen-reader user gets total silence for the entire 8-50s answer | `aria-live="polite"` status region, throttled — not raw token-by-token |
| F5-1 | A11y | P2 | S | `AdminShell.jsx:229-235`; `Sidebar.jsx:85-89` | Icon-only logout buttons use `title`, not `aria-label` (inconsistent with `ThemeToggle`, which does it right) | Fragile accessible name for a screen-reader user | Add matching `aria-label` |
| TEAMMATE | Docs | P2 | L | `docs/TEAMMATE_GUIDE.md` (840 lines, 12+ stale locations) | Most out-of-date doc in the repo — architecture diagram, setup steps, and troubleshooting all describe the retired Open-WebUI/port-3000 flow | The exact document a new teammate opens first, actively misleading | Full rewrite following the pattern already applied to `README.md`/`CLAUDE.md` — `[parallel-safe]` |
| CHAT-4 | Chat UX | P2 | — | `app/generation/generator.py:591-607` | General-knowledge fallback answered a request to write a poem, not just textbook actuarial questions | Off-topic scope creep — correctly disclaimed, not hallucinated, but a product-scope decision worth making deliberately | Product decision: tighten hybrid-mode gate to insurance/actuarial topics, or accept as a feature |
| ENG-4 | Testing | P2 | M | `eval/golden_set.jsonl` (1/72 `calculation`) | Golden set thin on numeric calculation relative to the prompt-engineering effort spent on that answer shape | Under-tests exactly the answer type CLAUDE.md flags as needing the most care | Add 5-8 more `calculation` items |
| CI-1 | Ops | P2 | S | `scripts/check.sh` (not git-hooked; doesn't run `npm run lint`) | Local CI-equivalent exists but only runs if a developer remembers to type it | Silent regressions between "should have been caught" and "was caught" | `.pre-commit-config.yaml` wiring `check.sh` + `npm run lint` |
| P2-T3 | Product | P3 | S | `app/config/settings.py:318-319` | Department codes (PTSP/DP/DVA) never expanded anywhere | Business-org jargon leaks exactly like engineering jargon would | Small `DEPARTMENT_LABEL` map |
| CHART-1 | Frontend | P3 | S | `OverviewView.jsx` "Tài liệu theo phòng ban" panel | Donut renders 100% "Không đặt" (nothing tagged) — dead weight, not a real KPI yet | Confusing, not actionable until department tagging is used | Hide until ≥1 doc has a department, or relabel the empty state explicitly |
| CHAT-5 | Chat UX | P3 | S | `frontend/src/chat/*` (no `document.title` usage) | Browser tab title never reflects streaming/loading state | No passive signal for a user who alt-tabs away mid-generation | `useEffect` toggling `document.title` while `busy` |
| SEC-G | Security | P3 | S | `app/main.py` (no header middleware) | No `X-Content-Type-Options`/`X-Frame-Options`/CSP anywhere | Low-urgency defense-in-depth gap for an internal LAN tool | Blanket response middleware, 2 headers |
| ENG-2 | Security | P3 | S | `app/accounts.py:123` | Password-hash comparison uses `!=` not `hmac.compare_digest` | Self-acknowledged minor timing side-channel, PBKDF2 cost dominates in practice | One-line swap |
| F3-2 | Frontend | P3 | S | `frontend/oxlintrc` generation | oxlint's hex/px enforcement rule is silently disabled — `npm run lint` passing ≠ token-compliant | The one rule that would've caught F3-1 doesn't run | Stopgap grep in `check.sh`, or find an oxlint-compatible equivalent |

**If you fix only three things, fix these:** SEC-A (the only finding that lets a stranger read
real document content with zero credentials), OPS-A (the deployment story is broken on a fresh
clone right now, and it's a `git add`), and WAIT-1/CHAT-1 together (the perceived-latency +
cancellation pair — independently flagged by three separate passes as the single biggest felt
difference available).

## 6.4 Roadmap

### Wave 0 — Ship blockers (do before anyone else sees this)
1. **SEC-A**: add a session check to `/documents/{id}/file` and `/view`; add a regression test. `[parallel-safe]`. Done when: sessionless request to either route returns 401/redirect once accounts are provisioned, and `tests/test_auth.py` asserts it.
2. **OPS-A**: `git add app/static/dist/` (verify it's the current build first — `cd frontend && npm run build`, diff against what's about to be committed). Done when: `git status --short app/static/dist` shows nothing, and a fresh clone serves `/`, `/chat`, `/admin`.
3. **SEC-B**: change `.env.example` so `API_HOST=0.0.0.0` documents `API_SHARED_SECRET` as a hard co-requirement, not a suggestion. Done when: the example file makes the pairing unmissable.

### Wave 1 — Smoothness (highest UX return per hour)
1. **WAIT-1**: "Đang tìm trong tài liệu…" status line in the empty assistant bubble until first token. Felt difference: turns a silent 8-50s stare into visible progress — the single most-requested fix across three independent passes. `[parallel-safe]`
2. **CHAT-1**: `AbortController` + visible "Dừng" button; server-side `is_disconnected()` check. Felt difference: a wrong question is no longer a forced one-way wait.
3. **REFUSAL-UI**: one-line comparison fix. Felt difference: every refusal becomes actionable instead of a dead end.
4. **P2-F1**: persist `messages` to `sessionStorage`. Felt difference: refresh/accidental-back no longer destroys a conversation.
5. **P2-C1/C2/C3**: Modal fixes (native-dialog swap, Enter-submit, Esc-close) — small, bundle together since they touch the same two files. `[parallel-safe]`
6. **CHAT-3**: composer autogrow.

### Wave 2 — Visual polish and design-system compliance
1. **F3-4**: port `useIsMobile()`/drawer pattern from `chat/ChatScreen.jsx` to `AdminShell.jsx`; make the KPI grid `auto-fit`. This is the highest-value visual fix in the audit — every admin screen inherits it.
   - *Before*: 5 fixed-width KPI cards truncate to "Số...", "Tài..." below ~900px; the 264px rail eats 70% of a phone screen.
   - *After*: rail collapses to a hamburger drawer below 640px (matching chat exactly); KPI grid reflows to 2-3 columns before 900px, 1 column below 500px.
2. **F3-3**: darken `--text-muted` in light theme to ≥4.5:1 (e.g. `#5F7488`).
3. **F3-1**: decide + fix landing-page theming (document as deliberate, or wire to tokens).
   - *Before*: landing is a fixed navy palette regardless of `prefers-color-scheme`, no toggle shown.
   - *After*: either an explicit one-line comment confirming this is intentional brand styling, or full token coverage matching chat/admin.
4. **CHART-1**: hide/relabel the department donut until real data exists.
5. **ENG-1**: swap `/chat`'s 5 hand-rolled buttons for the `Button` component.

### Wave 3 — Product gaps
1. **P2-J6**: minimum viable profile surface — one `/me` view, `POST /change-password`. `[parallel-safe]` once Wave 0/1 land.
2. **P2-F2**: thumbs-down feedback loop, log-only endpoint.
3. **P2-F3**: client-side filter on the documents table (defer server pagination).
4. **P2-T1/T2/T3**: terminology fixes — small, bundle together.
5. **CHAT-4**: product decision on hybrid-mode scope (poem/off-topic handling).

### Wave 4 — Engineering health
1. Extract `app/generation/pipeline.py` from `app/api/chat.py` (§1.1's proposed split — mechanical, no behavior change). `[parallel-safe]`
2. `MODE-1` + `CHAT-2`: fix refusal-mode mislabeling and thread `first_token_ms` through all 4 logging call-sites — makes the admin dashboard's KPIs trustworthy.
3. Frontend test suite: `markdown.jsx`'s pure functions first, then SSE parsing, then `useTheme.js`.
4. `CI-1`: pre-commit hook wiring `check.sh` + `npm run lint`.
5. `docs/TEAMMATE_GUIDE.md` full rewrite. `[parallel-safe]`, L effort but mechanical given the target state already exists in `README.md`/`CLAUDE.md`.
6. `SEC-C`/`SEC-D`/`SEC-E`/`SEC-F`/`SEC-G`/`ENG-2`: security hardening batch, none urgent individually, worth one sweep.
7. `F5-1`/`F5-2`: accessibility batch — `aria-label` fixes, then the larger `aria-live` design decision.

### Wave 5 — Nice to have
- `ENG-4`: broaden the golden set's `calculation` category.
- `CHAT-5`: tab-title streaming indicator.
- Bulk operations/export/undo for documents (all explicitly deferred as reasonable at current pilot scale, per Phase 2).

## 6.5 Quick wins (S effort, ≥P2 impact — one afternoon each)

1. **OPS-A** — commit `app/static/dist/` (literally `git add`).
2. **REFUSAL-UI** — one-line string comparison fix, independently flagged 3×.
3. **WAIT-1** — loading status line in the empty chat bubble.
4. **P2-C1** — swap native `confirm`/`alert` for the existing `Modal`.
5. **P2-C2** — Enter-to-submit in `EditModal`.
6. **P2-C3** — Esc-to-close on `Modal`.
7. **P2-T1** — one string fix in `UsersView.jsx`.
8. **P2-T2** — extract the doc_type label map (already exists as `EDIT_DOC_TYPE_OPTIONS`, just needs reuse).
9. **F3-3** — one token value change for `--text-muted`.
10. **F5-1** — `aria-label` on the two logout buttons.
11. **SEC-B** — `.env.example` copy change.
12. **SEC-E** — one added sentence to the system-prompt rule blocks.
13. **SEC-F** — scheme allowlist in `renderInlineRun`.
14. **SEC-G** — two response headers.
15. **ENG-2** — `hmac.compare_digest` swap.
16. **CHAT-5** — `document.title` toggle.
17. **CHART-1** — hide/relabel the empty department donut.
18. **MODE-1** — one post-generation check to fix refusal-rate undercounting.
19. **CI-1** — a `.pre-commit-config.yaml` file.

## 6.6 Unverified suspicions

Carried forward from Phases 1, 4, and 5 (each phase doc has the full context):

| # | Suspicion | How to confirm |
|---|---|---|
| 1 | `leaked_refusals: 1` present in both full RAGAS runs, not yet root-caused | `python eval/run_ragas.py`, inspect `gate.leaked_refusals[0]` |
| 2 | Zip/XML-bomb resilience for DOCX/XLSX uploads (no explicit decompression-ratio guard found) | Construct a 50MB-capped-but-GB-decompressed DOCX, observe ingestion behavior |
| 3 | `setup_native.sh`'s half-failure recovery (killed mid-model-download) | Kill it partway through, re-run, see if it resumes or needs `rm -rf .venv` |
| 4 | Does closing the tab mid-stream actually free the server-side Ollama call? | Send a question, close the tab in ~2s, watch `ollama ps`/CPU |
| 5 | Mid-stream Ollama failure — code suggests a graceful message, not verified live | `pkill -f ollama` 5s into a request, observe the browser |
| 6 | Two-tab/two-user concurrency — serialized or parallel? | Two parallel `curl` streams, compare TTFT |
| 7 | The other 5 of 6 prompt suggestions — only 1 was live-tested | One curl call per suggestion in `scripts/prompt_suggestions.json` |
| 8 | Login page's Tab3 landing on `<body>` — likely a CDP synthetic-input artifact | Real keyboard, real (non-headless) browser window |
| 9 | 200% browser zoom on all 3 surfaces | Actual Cmd/Ctrl-+ zoom, not `deviceScaleFactor` |
| 10 | Disk-full / corrupt-Qdrant-index / Ollama-OOM startup behavior — code suggests graceful, not triggered | Fill disk or truncate `qdrant_storage/`, restart |
| 11 | `logs/query_timings.jsonl` retention policy — no rotation/TTL code found | Confirm whether manual rotation is the intended design |
| 12 | 200MB PDF upload end-to-end | `dd` a 200MB file, attempt upload against synthetic data only |

---

*Screenshots referenced throughout: `audit/screenshots/` (19 images, 3 viewports × 2 themes ×
3 surfaces + states). Raw live-query transcripts and timing data referenced in `04-chatbot.md`
were kept in the session scratch directory (not committed — contain full model-generated answer
text, not repo-appropriate to commit verbatim); the timings and answer previews quoted in
`04-chatbot.md` are the citable record.*
