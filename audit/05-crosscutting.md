# Phase 5 — Cross-cutting

Date: 2026-08-08. Read-only. Accessibility findings come from a real keyboard-driven CDP session
(`Input.dispatchKeyEvent` Tab presses against the running app, not code-reading alone) plus a
grep pass; i18n/docs/resilience from code + config reading. Contrast ratios were already computed
in `audit/03-frontend.md` §3.3 (F3-3) — referenced, not re-derived, here.

## 5.1 Accessibility (WCAG 2.1 AA)

**Keyboard-only run, login page** (`app/templates/login.html`, 6 Tab presses from initial
`autofocus` on the email field): email(autofocus, implicit) → **Tab1** password input → **Tab2**
"Đăng nhập" submit button → **Tab3** landed on `<body>` (no focusable element — see caveat below)
→ **Tab4** "← Quay lại" back-link → **Tab5** wraps back to the email input → **Tab6** password
again. Order is logical (form fields → submit → secondary nav) and every stop except Tab3 shows
a real focus indicator: inputs get a 3px `box-shadow: var(--accent-subtle) 0 0 0 3px` ring,
buttons/links get the browser's native `outline: auto 1px rgb(0,95,204)`. **Caveat on Tab3**:
CDP's synthetic `Input.dispatchKeyEvent` doesn't always reproduce real hardware Tab-key focus
transitions exactly — this could be a harness artifact rather than a genuine dead stop in the
tab order (a real user tabbing with a physical keyboard may not experience this). Flagged as
**unverified** rather than asserted as a bug; worth a 30-second manual check with a real
keyboard before acting on it.

**Keyboard-only run, chat page** (as employee, 6 Tabs from page load): "+ Cuộc trò chuyện mới" →
theme toggle → logout (⏻) → the 3 visible prompt-suggestion cards, in visual (left-to-right,
top-to-bottom) order. All 6 stops show a visible focus ring (native blue outline or a card
shadow). **Positive finding**: focus-visible is never suppressed anywhere in the design system
(`frontend/src/tokens/` has no `outline: none` with no replacement, confirmed by these two live
runs finding a ring on every single stop) — a common, easy-to-miss failure mode that this app
doesn't have.

**Finding F5-1 (P2, S): icon-only buttons use `title` instead of `aria-label` — inconsistent
with the one component that gets it right.** `frontend/src/admin/AdminShell.jsx:229-235` (logout
button, `⏻` glyph) and `frontend/src/chat/Sidebar.jsx:85-89` (same logout button, duplicated)
both have `title="Đăng xuất"` and no `aria-label` — the button's only content is the `⏻`
character, which is a poor accessible name if a screen reader reads the glyph literally instead
of falling back to `title`. Compare `frontend/src/components/navigation/ThemeToggle.jsx:9`, which
correctly sets `aria-label="Toggle theme"` (in English, incidentally — a small language
inconsistency in an otherwise all-Vietnamese app, worth a matching Vietnamese `aria-label` while
fixing this). Fix: add `aria-label="Đăng xuất"` next to the existing `title` on both logout
buttons (title can stay, for the sighted-mouse-hover tooltip). S effort, 2 lines.

**Finding F5-2 (P2, M): no live region for streaming chat text — a screen-reader user gets
silence for the entire 8-50 second answer, then nothing announces that it finished.** Confirmed
by reading `frontend/src/chat/ChatScreen.jsx` and `ChatMessage.jsx` in full: neither the
streaming message container nor any wrapper has `aria-live`, `role="status"`, or `role="log"`.
A sighted user sees text appear incrementally; a screen-reader user gets no announcement at all
until they manually re-navigate to the message after guessing it's done. Fix: wrap the streaming
assistant bubble in `aria-live="polite"` (not `"assertive"` — that would interrupt on every
token) — a common pattern is to only mark the container live once, and let the browser's
mutation-based live-region behavior announce the accumulated text at a throttled rate, or
announce just a "Đang trả lời… / Đã trả lời xong." status change via a separate
`role="status"` element rather than the raw streaming text itself (announcing every token would
be unusable). M effort — needs a small design decision (what exactly gets announced), not just a
markup change.

**Landmarks & headings**: correct real semantic structure, not `<div>` soup — `landing/
LandingScreen.jsx` has `<header>`/`<main>`/`<h1>`, `chat/ChatScreen.jsx` has `<header>`/`<main>`,
`admin/AdminShell.jsx` has `<nav>`/`<main>`/`<header>`, and heading levels are used sensibly
(page `<h1>`, panel `<h2>`) in `OverviewView.jsx`/`DocumentsView.jsx`/`UsersView.jsx`. No
`role="navigation"`/`role="main"` ARIA needed or missing — the native elements already carry
those landmark roles implicitly.

**Form labels**: `app/templates/login.html:191-194` — real `<label for="email">`/`<label
for="password">` wired to matching `id`s. Correct. The admin document-upload form
(`frontend/src/components/forms/Input.jsx`) uses visible placeholder-style prose instead of
`<label>` elements for its text inputs ("Tên tài liệu (tuỳ chọn...)", "Nguồn URL công khai...")
— functional for sighted users (the description text sits directly above each field) but not
programmatically associated via `htmlFor`/`aria-labelledby`, so a screen reader announces these
inputs with no name. Not re-scored separately (folds into F5-2's general "streaming/dynamic
UI wasn't built with a screen reader in mind" pattern) but worth the same fix pass.

**Contrast**: see `audit/03-frontend.md` F3-3 — `--text-muted` fails AA in light mode specifically
(2.58:1, computed from the actual token hex values), passes in dark mode (5.54:1). Not
re-computed here; cross-referenced so the Phase 6 register has one canonical source for it.

**Zoom to 200%**: not tested in this pass (would need a real browser zoom, which
`Emulation.setDeviceMetricsOverride`'s `deviceScaleFactor` doesn't equivalently simulate) —
logged under Unverified suspicions.

## 5.2 Internationalization

Single-language app by design — no `i18n`/`useTranslation`/locale-switching library found
anywhere in `frontend/src` (confirmed via grep across the whole tree), every string is
hardcoded Vietnamese prose directly in JSX. Given the stated audience (Bảo Việt Life employees,
an internal Vietnamese-language tool), an English mode is very unlikely to be needed — **not a
finding**, just confirming the architecture matches the actual requirement rather than being an
accidental gap. If it ever became a requirement, hardcoded strings would mean a full
find-and-extract pass across every component; worth knowing that cost exists, not worth paying
it now.

**Locale-aware formatting**: correctly used where it matters —
`frontend/src/admin/OverviewView.jsx:447` and `DocumentsView.jsx:291` both format ingestion
timestamps with `new Date(...).toLocaleString("vi-VN")`. One inconsistency:
`OverviewView.jsx:118`'s question-count formats with a bare `.toLocaleString()` (no explicit
locale argument, so it silently follows the browser's runtime locale instead of always
formatting as `vi-VN` like every other number/date on the same dashboard) — cosmetic (VN and
default JS number grouping mostly agree for small integers) but worth the one-argument fix for
consistency's sake. No currency values were found rendered anywhere in the UI to check for
`₫`/VND formatting.

## 5.3 Documentation

**`README.md` / `CLAUDE.md`**: both were updated as part of this session's own Open-WebUI-removal
work (immediately prior to this audit) and, checked again here, correctly describe the CURRENT
single-port/RBAC architecture — no lingering "port 3000" or "Open WebUI" references in either
file (confirmed via `grep -rn "3000\|Open WebUI" README.md CLAUDE.md`: only the intentional
"Open WebUI has been retired" sentences remain, which are correct as written). These are
accurate as of this audit.

**`docs/TEAMMATE_GUIDE.md` — CONFIRMED stale (inherited finding, quantified here).** 840 lines,
at least 12 distinct locations still describe the retired architecture as current: an ASCII
architecture diagram showing Open WebUI on port 3000 talking to FastAPI on 8000 (lines 106-107),
"User hàng ngày chủ yếu dùng Open WebUI `:3000`" (line 121), a components table row saying the
frontend IS Open WebUI 0.5.4 (line 144) and upload happens via an "Open WebUI Pipe" (line 145),
setup instructions creating a `.venv-webui` that no longer exists (line 412), and a startup
step describing "Ollama + FastAPI + Open WebUI" as the three services to start (line 416) when
it's now two. This is the single most out-of-date document in the repo and is exactly the kind
of thing a new teammate would open first and be actively misled by. Fix: full rewrite following
the same pattern already applied to `README.md`/`CLAUDE.md` this session — replace the
architecture diagram, drop every `.venv-webui`/port-3000/Pipe reference, update the
components table's Frontend/Upload rows to describe `/chat` and the admin upload form. L effort
given the file's length, but mechanical once the target state is defined (it already is, in the
other two docs) — a good candidate for a `[parallel-safe]` task handed to a fresh agent with
`README.md` as its reference.

**`data/glossary/README.md` / knowledge-pack docs / skill file**: not re-audited here (out of
this phase's scope); `.claude/skills/insurance-rag-pipeline/SKILL.md` was already spot-corrected
for its two Open WebUI mentions earlier this session (per the conversation record) — confirmed
still correct (`grep` for "Open WebUI" in that file now only matches the historical/removed
context, not a live claim).

## 5.4 Resilience

Not load-tested or destructively tested against the shared, currently-running dev server (doing
so would have disrupted Phases 1-4's concurrent use of the same Ollama/Qdrant instance) — this
section is a code-level assessment, with live-test repro commands deferred to Unverified
suspicions.

**Upload limits — real and graceful.** `app/config/settings.py:305` (`max_upload_mb: int = 50`)
enforced in `app/api/ingest.py:145-167`: the upload is streamed to disk and rejected mid-stream
once it crosses the limit ("never leaves anything on disk" per the function's own docstring,
line 151), returning a plain Vietnamese error ("Tệp vượt quá giới hạn 50 MB cho phép.") rather
than a raw exception. A comment at `ingest.py:247` (tagged `SEC4`) documents that an earlier
version of this code left orphaned unindexed files on disk on failure — since fixed. A 200MB PDF
upload (per the prompt's specific ask) should therefore fail cleanly at the byte-count check
well before parsing even starts — not verified live, but the code path is unambiguous.

**Service-down legibility**: `scripts/healthcheck.sh` gives a real, readable
`[ OK ]`/`[FAIL]` smoke test per service (Ollama, Qdrant, the API) rather than a silent hang, and
`app/main.py`'s `lifespan()` (read in Phase 0) logs specific, actionable warnings for each
degraded-but-not-fatal startup condition (no accounts provisioned, no session secret, loopback
citation base, open LAN without a shared secret) instead of failing to start or failing silently.
`app/api/chat.py`'s `_RETRIEVAL_EXCEPTIONS` wrapper (confirmed present, referenced in
`audit/00-system-map.md` §0.5 as a roadmap.md-tracked fix) turns a Qdrant-down or
retrieval-crash mid-request into the same graceful Vietnamese error message pattern used
elsewhere, rather than a raw 500.

**Not verified live** (see Unverified suspicions): disk-full behavior during ingestion, a
corrupt/truncated Qdrant index at startup, Ollama OOM mid-generation (Phase 4 covers the
mid-stream-failure code path but not an actual live kill), and 50-concurrent-user load. None of
these were exercised — this section describes what the code *appears* built to handle, not what
was *observed* to happen under those conditions.

## 5.5 Privacy/compliance posture

Largely covered by Phase 1's security audit (`audit/01-engineering.md` §1.4) — not duplicated
here. The one item specific to this phase: `app/query_timing.py`'s own module docstring (lines
1-21, read in Phase 4) explicitly states the timing log is "metadata-only... deliberately
records NO query or answer text" and lists exactly what it does keep (timings, mode label, hit
doc_ids/section_paths/scores, character counts) — confirmed by reading `log_query_timing`'s
actual record-building code (`query_timing.py:102-125`), which matches the docstring's claim
field-for-field. This is a genuinely good, verifiable privacy design, not just a comment — worth
protecting explicitly in Phase 6 as "don't touch without re-reading this doctoring first," since
it would be easy for a future feature (e.g. F3-1's "show the actual question in an audit trail")
to quietly violate it. An auditor asking "what do you log and for how long" has a real, honest
answer here: coarse metadata only, retained until manually rotated (`logs/query_timings.jsonl`
has no automatic rotation/TTL found in this pass — worth confirming retention policy is a
conscious choice, not an oversight).

## Unverified suspicions (Phase 5)

1. **Login-page Tab3 landing on `<body>`** — likely a CDP synthetic-input artifact, not
   necessarily a real keyboard-navigation dead spot. Confirm with a real keyboard and a real
   (non-headless) browser window.
2. **200% browser zoom** — not tested; `Emulation.setDeviceMetricsOverride`'s scale factor isn't
   an equivalent simulation. Confirm with actual Cmd/Ctrl-+ zoom in a real window on `/`, `/chat`,
   `/admin`.
3. **Disk-full / corrupt-Qdrant-index / Ollama-OOM startup behavior** — code suggests graceful
   handling (see §5.4) but none of the three was actually triggered. Confirm by filling
   `/tmp` (or wherever Qdrant's embedded storage lives) to capacity and re-running
   `scripts/run_native.sh`, or truncating a file inside `qdrant_storage/` and restarting.
4. **`logs/query_timings.jsonl` retention** — no rotation/TTL code found; confirm whether this
   is intentional (manual rotation by an admin) or a gap, and what an auditor would expect here.
5. **200MB PDF upload** — the byte-limit code path is unambiguous but not exercised end-to-end;
   confirm with `dd if=/dev/zero of=/tmp/big.pdf bs=1M count=200` and a real upload attempt
   against `/ingest` (as admin, against `data/synthetic/`-scale test data only — never against
   `data/real/`).
