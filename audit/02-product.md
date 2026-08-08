# Phase 2 — Admin & Users: features, logic, professionalism

Read-only phase. Verified against the running server (`http://127.0.0.1:8000`,
Ollama + Qdrant up) via `curl` with the two seeded demo accounts, and against
the JSX/Python source in the current (uncommitted) working tree. Every claim
below is either a file:line citation or a command whose real output is quoted
inline. No screenshots were taken (that is Phase 3's job with browser tools);
anywhere a claim would benefit from a screenshot I don't have, it's flagged
explicitly rather than asserted as a visual fact.

Evidence standard per `AUDIT_PROMPT.md`: severity `P0` blocker / `P1` major /
`P2` minor / `P3` polish; effort `S` (<1h) / `M` (half-day) / `L` (multi-day).

---

## 2.1 Journey walkthroughs

### Journey 1 — Land on `/` → understand what this is → log in → ask a first question

1. `GET /` is public (`app/auth.py:68-77` `PUBLIC_PREFIXES` includes `"/"`
   exact-match only). Renders `frontend/src/landing/LandingScreen.jsx`: navy
   hero, one sentence of positioning ("Mọi câu trả lời, kèm nguồn trích dẫn
   rõ ràng"), three value props (grounded-in-documents, full Vietnamese,
   stays on the internal network), one CTA ("Đăng nhập"). This is honest and
   uncluttered — it does not oversell. **Good, don't touch.**
2. CTA → `/login` (`frontend/src/landing-main.jsx:9`: `window.location.href =
   "/login"`). `app/templates/login.html` is a plain Jinja-free page sharing
   the same navy rail / gold-triangle brand language as the landing page —
   visually continuous, no jarring style jump. It states "Dùng tài khoản
   email @baoviet.com được cấp cho bạn" (use the @baoviet.com account issued
   to you) — correctly sets the expectation that this is provisioned, not
   self-service.
3. Live-verified login: `POST /login` with the seeded admin and employee
   accounts both return `200 {"ok":true,"role":"admin"|"employee"}` and set
   `bv_admin_session` (`app/api/login.py:31-54`). `login.html:229-230` routes
   an admin to `/admin`-or-`?next=`, and forces an employee to `/chat/` even
   if `?next=/admin/...` was present — verified this is not just client-side
   theater: `GET /admin/` with an employee cookie and `Accept: text/html`
   returns `303 → /chat/` server-side (`app/main.py:180-182`), and the same
   request with a non-HTML `Accept` returns `403 JSON` — both enforced in
   `admin_session_gate`, not just the redirect.
4. First question, live-verified (employee account, real Ollama+Qdrant):
   `Công ty chi trả Số tiền bảo hiểm trong trường hợp nào theo sản phẩm An
   Tâm Bảo Vệ?` → grounded, correctly cited answer in 57s wall time (see
   Journey 5 / timing note below — full latency analysis is Phase 4's job,
   but the number is relevant here because of what the UI does *not* show
   during that wait, see Finding P2-J1 below).

**Finding P2-J1 (P2, effort S).** During the 25–57s gap between send and
first token (measured live, two different queries), the assistant bubble
renders with **zero loading affordance**. `ChatScreen.jsx:49` immediately
pushes `{ role: "assistant", text: "", streaming: true }`, and
`ChatMessage.jsx:129` renders `renderMarkdown(body || " ")` — an empty
paragraph. The only visible state change is the composer's send button
going grey (`Composer.jsx:68-69`, disabled while `busy`). A first-time user
watching a blank space for up to a minute with no "đang tìm tài liệu…" /
spinner / skeleton has no way to distinguish "working" from "broken." This
is exactly the gap `AUDIT_PROMPT.md` calls "the single biggest
perceived-quality lever." Fix: render a lightweight status line ("Đang tìm
trong tài liệu…") in the assistant bubble until the first delta arrives.

### Journey 2 — Follow-up → citation → source document → back

1. Verified: `SourcePanel.jsx` opens on citation click and calls
   `/documents/{id}/view` (or `/file` for PDFs/images, `app/api/ingest.py:342-366`).
   Live-verified this route is public even for an unauthenticated request
   (`curl` with no cookie → `200`) — correct by design (`app/auth.py:79-84`
   `_PUBLIC_DOC_RE`, since citation links must resolve for a signed-in
   employee reading in a new tab, and the doc_id is opaque). "Come back" is
   just closing the panel (`onClose`, ✕ button) — the chat thread underneath
   is untouched, no navigation occurred, so no lost state. **Good.**
2. **Finding P2-J2 (P2, effort S).** The sources block returned by the
   backend lists up to 5 retrieved chunks (`Nguồn tham khảo:` block), but
   the model's prose only inline-cites a subset — in the live test above,
   the answer body cited only `[1]`, yet `CitationRow` in `ChatMessage.jsx:7-62`
   renders chips for all 5 listed sources ("Nguồn · 5"), including `[2]`–`[5]`
   which never appear as a marker in the readable text. A user who reads the
   prose (sees no `[2]`) and then opens "Nguồn 2" in the citation row is
   looking at a document the answer never actually pointed to — undermines
   the trust the citation feature exists to build. Either only render chips
   for `n`s that appear in `body`, or visually distinguish "cited inline" vs
   "also retrieved."
3. Follow-up question / pronoun continuity is exercised by
   `app/retrieval/conversation_scope.py` and `query_rewrite.py` server-side —
   this is functional and out of scope to re-verify here (Phase 4 covers
   multi-turn accuracy in depth); the client-side mechanics are sound
   (`ChatScreen.jsx:48` sends full prior turns as `history` on every send).
4. **Finding P2-J2b (P2, effort S).** Refreshing the browser mid-conversation
   (or after step 2's "come back") **loses the entire thread** — confirmed
   in code: `ChatScreen.jsx:25` `useState([])` with no `localStorage`,
   `sessionStorage`, or server-side history fetch anywhere in `chat/api.js`
   or `ChatScreen.jsx`. See Feature completeness §2.2 for the full
   persistence gap.

### Journey 3 — Bad/refused answer → understand why → recover

1. Live-verified with a deliberately out-of-scope question
   (`Giá cổ phiếu Bảo Việt hôm nay là bao nhiêu?` — a stock-price question
   the corpus cannot answer): the backend returned exactly
   `"Tôi không tìm thấy thông tin trong tài liệu.\n\n_⏱ Thời gian trả lời: 25s_"`
   — correct, honest refusal per `CLAUDE.md`'s answering rules, no
   hallucination, no invented exclusion reasoning.
2. **Finding P2-J3 (P2, effort S) — the "understand why → recover" UI path
   is dead code.** `ChatMessage.jsx:5` defines
   `REFUSAL_TEXT = "Tôi không tìm thấy thông tin trong tài liệu."` and
   `ChatMessage.jsx:116`: `isRefusal = !streaming && text.trim() === REFUSAL_TEXT`.
   This is meant to swap in the friendlier `NoAnswer()` component
   (`ChatMessage.jsx:88-94`: *"Tôi không tìm thấy thông tin này trong các
   tài liệu bạn có quyền truy cập. Hãy thử nêu rõ tên sản phẩm, hoặc diễn
   đạt lại câu hỏi."* — a real, actionable recovery suggestion). **But every
   answer, refusals included, has the `"⏱ Thời gian trả lời: Ns"` footer
   appended server-side** (`app/query_timing.py:79-86`,
   `response_time_footer()`, called unconditionally). So the live string is
   never byte-equal to `REFUSAL_TEXT` — confirmed with the actual captured
   response above. `isRefusal` is **always false in production**, so users
   see the raw two-paragraph text (refusal sentence, then an italic timing
   line) rendered through the generic markdown path, with **no rephrase
   suggestion and no distinct visual treatment** from a normal answer. This
   directly fails the "recover" half of this journey. Fix: compare against
   `text.startsWith(REFUSAL_TEXT)` (or strip the footer before comparing) —
   one-line change, high UX payoff, exactly the kind of item
   `AUDIT_PROMPT.md §6.5` asks for in "quick wins."
3. Once a user reads the refusal, there is no next-step UI beyond retyping
   in the composer — no "suggested rephrasing" chips, no link back to the
   empty-state's prompt suggestions. Minor (`P3`) given the fix in #2 above
   would already restore the intended text-level suggestion.

### Journey 4 — Admin: upload → process → verify searchable → edit metadata → delete → confirm gone

1. Upload (`DocumentsView.jsx` `UploadCard`, `POST /ingest`,
   `app/api/ingest.py:218-256`, admin-gated
   `Depends(auth.require_admin)` — live-verified: employee `GET /documents`
   → `403 {"detail":"Chỉ quản trị viên (admin) mới có thể thực hiện thao
   tác này."}`). Status copy during upload: *"Đang nạp "…"… (có thể mất một
   lúc do enrichment công thức)"* — sets a real expectation (slow ≠ broken)
   rather than a bare spinner. **Good.**
2. "Watch it process": there is no progress bar or step indicator (parse →
   chunk → enrich → index) — a single "uploading…" string covers what can be
   a multi-minute pipeline for a formula-heavy PDF (`enrichment.py` LLM
   calls). Given how variable ingestion time is (a one-page glossary vs. a
   50-page PDF with tables), a flat status string with no elapsed-time or
   step feedback is a `P2` gap, but the disclaimer text at least manages
   expectations honestly. Effort to add a real progress indicator would be
   `M` (requires either polling or SSE from `/ingest`, currently a single
   blocking `await run_in_threadpool(...)`, `app/api/ingest.py:242-244`).
3. "Verify it's searchable": there is no "test this doc" affordance directly
   on the row after upload — the admin has to separately go find the "Hỏi
   thử nhanh" panel at the bottom of the *Overview* tab (a different nav
   item) to ask a question against it. Verified this panel exists
   (`OverviewView.jsx:253-317`, calls raw `/v1/chat/completions` and shows
   un-rendered LaTeX with a code-block disclaimer — intentionally minimal,
   documented as such in a comment). Functionally fine, but discoverability
   is poor: a brand-new admin has no reason to expect a chat-testing tool to
   live inside the metrics dashboard. `P3`, effort `S` — a one-line hint or
   link from the Documents page ("Kiểm tra tài liệu này trong Tổng quan →")
   would close the gap cheaply.
4. Edit metadata (`EditModal`, `PATCH /documents/{id}`,
   `app/api/ingest.py:459-471`, admin-gated). Renaming correctly warns the
   user it will **re-run the full ingestion pipeline** (*"Đổi tên sẽ nạp
   lại tài liệu từ tệp gốc... có thể mất một lúc"*, `DocumentsView.jsx:173-176`)
   — accurate, matches the backend (`app/api/ingest.py:393-449`,
   `title_changed` branch does a full `_run_pipeline` re-embed). Good, honest
   copy about a genuinely slow operation.
5. Delete (`handleDelete`, `DocumentsView.jsx:233-244`): uses the browser's
   native `window.confirm()` / `window.alert()` rather than the app's own
   `Modal` component (which IS used two lines away for Edit). See Finding
   P2-C1 below (Interface consistency) — same underlying issue, listed once
   there to avoid double-counting.
6. "Confirm it's gone from answers": live-verified the delete endpoint
   itself works correctly and returns a real error for a bad id
   (`DELETE /documents/does-not-exist` → `404
   {"detail":"Không tìm thấy tài liệu với doc_id này."}` — Vietnamese,
   specific, actionable). There is, however, **no in-UI confirmation loop**
   telling the admin the document is now unreachable from `/chat` — the
   admin has to trust the delete succeeded (table refresh) and separately
   go ask the assistant a question to be sure. Reasonable for a v1, `P3`.

### Journey 5 — Admin: read metrics/overview, answer "is the system healthy today?"

1. Live-verified `GET /metrics/summary?hours=24` (admin session) returns a
   real, non-fabricated snapshot: `n_requests: 6`, `refusal_rate: 0.0`,
   `elapsed_ms_p50: 25215`, `elapsed_ms_p95: 56689`, mode breakdown, daily
   volume, heatmap, top documents, latency histogram, department donut, and
   recent-ingest list (`OverviewView.jsx:319-462`). This is a genuinely
   useful, well-organized single screen — 5 KPI cards up top, then charts —
   and it answers "is the system healthy" better than a raw log tail would:
   Ollama/Qdrant up/down badges live in the sidebar
   (`AdminShell.jsx:239-241`, polled every 15s), refusal rate and p50/p95
   latency are both `betterWhen="down"`-tagged KPIs. **This is the strongest
   screen in the admin console — genuinely good, don't touch the structure.**
2. One inconsistency worth flagging for trust: in the same live session, a
   deliberately out-of-scope question (Journey 3) produced the exact
   `REFUSAL_TEXT` string, yet the metrics snapshot taken immediately after
   showed `"refusal": 0` in `mode_breakdown` (`n_requests: 6` total for the
   window, of which the earlier requests plus this one should include at
   least one refusal). This could not be root-caused in this read-only phase
   (`P3`, needs a follow-up run correlating `logs/query_timings.jsonl`
   directly against the exact request that produced the refusal) — noted
   under Unverified suspicions below rather than asserted as a confirmed bug.
3. No comparison/trend arrows on the KPI cards themselves (just the current
   window's number) — this is explicitly Phase 3's territory
   (`AUDIT_PROMPT.md §3.5` "is the number the hero, is there a
   comparison/trend"), not re-litigated here.

### Journey 6 — Account lifecycle: provisioning, first login, password change, forgotten password, deactivation

This is the journey `AUDIT_PROMPT.md` explicitly predicts will be "probably
the biggest product gap." Confirmed, plainly:

- **Provisioning**: `scripts/seed_accounts.py` — a CLI script run by hand on
  the server (`python scripts/seed_accounts.py email pw role`). No in-app
  account creation exists anywhere; `POST /accounts` doesn't exist —
  `app/api/login.py` only defines `GET /accounts` (list, admin-only,
  read-only, live-verified: `list_accounts()` returns `email + role` only,
  never a password hash — correctly scoped). **P1, effort M**: any admin who
  needs to add a new employee needs shell access to the server, not just the
  `/admin` role — this is a real operational bottleneck, and `UsersView.jsx`
  visibly says so in its own hint text (see below), which is honest but
  doesn't reduce the gap.
- **First login**: the password set by `seed_accounts.py` is the permanent
  password. There is **no forced password change on first login** — grepped
  `app/api/login.py` (83 lines total) and `app/accounts.py` (144 lines
  total) end to end: no `must_change_password` flag, no first-login branch
  anywhere. Whoever ran the script (presumably IT/the manager) knows every
  employee's password indefinitely unless they re-run the script.
- **Password change (self-service)**: **does not exist.** Confirmed by
  reading every route in `app/api/login.py` — the full route list is
  `GET /login`, `POST /login`, `POST /logout`, `GET /me`, `GET /accounts`.
  There is no `PATCH /me`, no `POST /change-password`, nothing. No profile
  page anywhere in `frontend/src/admin/` or `frontend/src/chat/`.
- **Forgotten password**: **no such route, no such link.** Read
  `app/templates/login.html` in full (246 lines) — there is no "Quên mật
  khẩu?" link, no email-based reset flow (consistent with `accounts.py`'s
  own docstring: *"no self-service signup and no email-sending"*). Today an
  employee who forgets their password has to ask an admin to re-run
  `seed_accounts.py` with `overwrite=True` — which silently resets the
  password with no notification to the account holder.
- **Deactivation**: **does not exist as an operation.** `UsersView.jsx` is
  read-only by its own explicit admission (`UsersView.jsx:30`, hint text):
  *"Chỉ xem — chưa có tạo/xoá tài khoản qua giao diện, dùng
  scripts/seed_accounts.py trên máy chủ"* ("View only — no create/delete via
  the interface yet, use `scripts/seed_accounts.py` on the server"). There
  is no `DELETE`/deactivate endpoint in `accounts.py` at all — an offboarded
  employee's account stays valid indefinitely unless someone with server
  access manually edits `data/accounts.db` (there's no CLI helper for
  deletion either, only create/overwrite).

**Rollup finding P2-J6 (P1, effort M for a minimum viable fix — see §2.2
"minimum viable profile surface" below for the concrete smallest change).**
Account lifecycle is entirely a server-shell operation today. For a handful
of pilot users this is tolerable (and honestly disclosed in the UI, which is
worth crediting), but it does not scale past a small pilot without either
routine IT involvement for every password reset or a real security risk
(shared/known passwords, no deactivation on offboarding — see Phase 1 for
the security framing of this same gap).

---

## 2.2 Feature completeness

### No conversation persistence

Confirmed in code (see Journey 2 above): `ChatScreen.jsx:25` holds messages
in a plain `useState([])`, no read/write to `localStorage`,
`sessionStorage`, IndexedDB, or any server endpoint. `CLAUDE.md` documents
this as a deliberate current-state fact ("Chat history is in-memory per
page load; there is no conversation persistence"), not a bug — but it is
still the single biggest thing that breaks an ordinary use pattern: **any
refresh, accidental back-button, tab close, or crash loses the entire
conversation**, including a long multi-turn thread the employee may have
spent several minutes building context in.

**Recommended smallest fix (P1, effort S–M):** persist `messages` to
`sessionStorage` (keyed per tab, cleared on tab close — no new backend
surface, no schema, no privacy-review overhead since nothing leaves the
browser) on every update in `ChatScreen.jsx`, and rehydrate on mount. This
alone fixes "refresh loses everything" without touching the server. A real
server-side persisted-thread history (survives across devices/browsers) is
a larger, `L`-effort feature and is not the "smallest change" the audit
prompt asks for — flag it as a Wave-3-scale item, not a quick win.

### No self-service anything (password reset, profile, settings)

Covered exhaustively in Journey 6. **Minimum viable profile surface**
(concrete, not hand-wavy): a single `/me` page or modal reachable from the
existing email chip in `Sidebar.jsx`/`AdminShell.jsx` with exactly two
fields: current password + new password, posting to a new `POST
/change-password` (needs `app/accounts.py` to gain an `update_password`
function — currently only `create_account(..., overwrite=True)` exists,
which is a full account rewrite, not a scoped password-only update, but the
underlying PBKDF2 hashing logic is already there and directly reusable).
Effort: `M` (new backend route + one new small frontend view). This alone
would close the worst of "no self-service" without attempting full account
lifecycle (create/deactivate), which is fairly reasoned to stay
admin/script-only for now given the account-count scale (`CLAUDE.md`:
"reasonable for a handful of internal accounts").

### `UsersView.jsx` (46 lines) vs `OverviewView.jsx` (462 lines)

Confirmed: `frontend/src/admin/UsersView.jsx` is exactly what its line count
suggests — a read-only table (`Table` component, columns `Email`, `Vai
trò`) fed by `GET /accounts`, with zero interactive elements beyond the
implicit page. **What an admin can do here: see who has an account and what
role they hold. Nothing else.** No create, no edit, no role change, no
delete, no search box, no last-login timestamp, no "account created" date.
This is not a stub hiding unfinished wiring — it is an honest, complete
implementation of a deliberately minimal feature (the hint text says so
outright, see Journey 6). The gap is real (P1 per Journey 6's rollup), but
the code itself isn't broken or misleading — it's exactly as capable as it
admits to being, which is a different (better) finding than "half-built
feature nobody finished."

### Search/filter/sort/pagination in the documents table

Confirmed absent. `Table.jsx` (26 lines, `frontend/src/components/data/Table.jsx`)
implements exactly: a `<table>`, hover-highlight rows, an empty state. No
`onClick` on any `<th>`, no sort icon, no controlled sort state anywhere in
`DocumentsView.jsx`. No search `<Input>` above the documents table (contrast
with `OverviewView.jsx`'s `AskPanel`, which does have a text input — the
absence in Documents is a real gap, not a missing component). No pagination
— `fetchDocuments()` (`admin/api.js:34-38`) fetches the entire list in one
call and renders every row.

**At realistic scale:**
- **50 docs**: fine, a single unsorted table is still scannable.
- **500 docs**: the table becomes a scroll-and-hope experience — no way to
  find "the An Bình Trọn Đời policy" except reading every row or using the
  browser's own Ctrl+F, which won't match anything hidden by truncation.
- **5000 docs**: the page fetches and renders 5000 DOM rows in one shot —
  `list_documents()` (`app/api/ingest.py:264-269`, backed by
  `indexer.list_documents()`, a Qdrant scroll with no `limit`/`offset`
  params anywhere in the route signature) has no server-side pagination
  either, so this would be a real performance problem on both ends, not
  just a UX one.

`P2` at current pilot scale (a handful of synthetic + eventually a
department's real documents), trending toward `P1` if the real corpus grows
past a few hundred documents. Effort: `M` — add a client-side filter `Input`
first (cheapest, works fine up to low hundreds of rows since the full list
is already fetched), defer server-side pagination until document count
actually approaches thousands.

### Bulk operations, undo, confirmation for destructive actions

- **Bulk**: no multi-select anywhere (Documents or Users). Given the
  single-file upload flow and small pilot scale, `P3` — not worth building
  ahead of a real multi-hundred-document need.
- **Undo**: none. Delete is immediate and permanent (Qdrant points removed,
  `indexer.delete_document`) with no soft-delete/trash. The confirmation
  copy is honest about this — *"Thao tác này không thể hoàn tác"* ("cannot
  be undone", `DocumentsView.jsx:234`) — so the irreversibility is at least
  disclosed, not hidden. `P2`, effort `L` if a real trash/undo were wanted
  (would need Qdrant payload soft-delete + a restore path); not recommending
  it for this scale, just naming the tradeoff.
- **Confirmation dialogs use the browser's native `window.confirm` /
  window.alert`, not the app's own `Modal` component** — see Finding P2-C1
  in §2.3 (Interface logic & consistency), where it's analyzed alongside the
  rest of the modal/keyboard-behavior audit rather than duplicated here.

### Export (answers, metrics, document lists)

Confirmed absent everywhere — no CSV/JSON export button on
`OverviewView.jsx`, `DocumentsView.jsx`, or `UsersView.jsx`. Nobody has
asked for it yet per the available project history, and for an internal
tool at this scale it's reasonably deferred — `P3`, not a current pain
point. If an admin ever needs a document inventory for an offline audit,
today's only path is manually reading the table or querying
`logs/query_timings.jsonl`/`data/accounts.db` directly on the server —
acceptable for a single admin, not for a compliance handoff.

### Feedback loop (flag a wrong answer)

Confirmed absent. `ChatMessage.jsx`'s `MessageActions` component
(`ChatMessage.jsx:64-86`) offers exactly two actions: "Chép" (copy) and
"Tạo lại" (regenerate). No thumbs-up/down, no "báo lỗi" (report issue), no
free-text feedback field anywhere in `frontend/src/chat/`. This matches
`docs/audit/roadmap.md`'s own honest accounting (Day 7's "deliberately NOT
doing this week" list explicitly names "Thumbs-up/down capture... needs new
instrumentation *and* a product decision... before any code" — so this is a
tracked, acknowledged gap, not a fresh discovery). Re-affirming the
assessment: **without any feedback loop, there is no signal path from "the
assistant gave someone a wrong or unhelpful answer" back to whoever curates
the corpus or tunes retrieval** — the golden-set/RAGAS evaluation in `eval/`
is the only quality signal today, and it only covers questions someone
thought to write down in advance. `P1` (this is how quality silently rots
in production), effort `M` for the minimum version: a thumbs-down icon next
to "Tạo lại" that POSTs `{message_id/turn_index, query, answer, reason?}`
to a new log-only endpoint (no UI needed on the admin side yet — even
appending to a JSONL file next to `logs/query_timings.jsonl` would be a
real improvement over nothing).

---

## 2.3 Interface logic & consistency

### Terminology table (Vietnamese → English/meaning → where used)

| Vietnamese term | English / meaning | Where used | Consistent? |
|---|---|---|---|
| Tài liệu | Document | Documents view title, Overview panels, chat citations, upload/edit forms | Yes |
| Đoạn | Chunk (retrieval unit) | `n_chunks` display in Documents ("22 đoạn") and Overview ("Số đoạn truy xuất TB") | Yes — engineering term "chunk" is never leaked, consistently translated |
| Nguồn / Nguồn tham khảo | Source / Citation | `SourcePanel.jsx` header ("Nguồn N"), `CitationRow` ("Nguồn · 5"), backend's `**Nguồn tham khảo:**` block (`prompts.py`) | Yes |
| Người dùng | Users | Admin nav item (`AdminShell.jsx` "Người dùng") | Yes, matches `UsersView.jsx` title "Người dùng" |
| Tài khoản | Account | `UsersView.jsx` card title "Tài khoản đã cấp", login page copy | Yes, but see Finding P2-T1 below on the *accuracy* of one usage |
| Quản trị viên | Admin (role) | `ROLE_LABEL` in `UsersView.jsx`, `AdminShell.jsx` sidebar footer, `admin_session_gate` error text | Yes, identical string in all three places |
| Nhân viên | Employee (role) | Same three places as above | Yes |
| Đăng nhập / Đăng xuất | Log in / Log out | Landing CTA, login page, both sidebars | Yes |
| Cuộc trò chuyện mới | New chat/conversation | `Sidebar.jsx` "New chat" button, `ChatScreen.jsx` header default title | Yes |
| Trò chuyện | Chat | Page `<title>`, AdminShell's "Mở giao diện trò chuyện ↗" link | Yes |
| Có căn cứ / Tư vấn / Kiến thức chung / Từ chối / Khác | grounded / advisory / hybrid / refusal / other (answer mode) | `MODE_LABELS` in `OverviewView.jsx` only | Translated **only** here — see Finding P2-T2 |
| `policy` / `procedure` / `form` / `spreadsheet` / `image` / `figure` / `glossary` / `reference` / `other` | doc_type enum | `DocumentsView.jsx` table cells (`<Tag>{d.doc_type}</Tag>`), `OverviewView.jsx` recent-documents list (`{d.doc_type} · {d.n_chunks} đoạn`) | **Not translated — raw English enum value shown verbatim inside otherwise all-Vietnamese sentences.** See Finding P2-T2. |
| `PTSP` / `DP` / `DVA` | Department codes | `DocumentsView.jsx` department `<Select>`, table column, `OverviewView.jsx` donut chart labels | **Never expanded to a full department name anywhere in the codebase** (checked `app/config/settings.py:318-319`, the only place the three codes are defined — no comment naming what they stand for). See Finding P2-T3. |
| Phòng ban | Department | Column headers, form labels | Yes |
| Loại tài liệu | Document type | Column header, form label | Yes (the *label* is consistently Vietnamese even though the *value* isn't, see P2-T2) |

**Finding P2-T1 (P2, effort S).** `UsersView.jsx:24` describes the account
list as *"Tài khoản đăng nhập trang quản trị (email @baoviet.com)"* — "login
accounts **for the admin page**." This is factually wrong under the current
RBAC model: every provisioned account (`employee` role included) is
primarily a `/chat` account; only `admin`-role accounts additionally reach
`/admin`. A new admin reading this list would reasonably conclude every
listed account is an admin-console account, when most of them (in a
realistic deployment) will be employee/chat-only accounts. This reads like
leftover copy from before the RBAC split (when there was one shared
`ADMIN_PASSWORD` gating a single admin page — see `app/auth.py`'s own
module docstring for that history). Fix: *"Tài khoản đăng nhập hệ thống
(dùng cho /chat, và /admin nếu là quản trị viên)"* or similar — one string
change.

**Finding P2-T2 (P2, effort S).** Two enums are handled inconsistently in
the same admin console. `mode_breakdown`'s five values are translated to
Vietnamese labels (`OverviewView.jsx:5`, `MODE_LABELS`), but `doc_type`'s
nine values are shown as **raw English database enum literals** wherever
they're displayed as data (`DocumentsView.jsx:288`: `<Tag key="type">{d.doc_type}</Tag>`;
`OverviewView.jsx:443`: `{d.doc_type} · {d.n_chunks} đoạn`) — even though the
*input* dropdowns for the same field ARE bilingual
(`DOC_TYPE_OPTIONS`/`EDIT_DOC_TYPE_OPTIONS`, `DocumentsView.jsx:5-28`, e.g.
`"policy — Hợp đồng / Quy tắc bảo hiểm"`). So an admin picks a
Vietnamese-labeled option when uploading, then sees the bare English code
("policy", "glossary", "other") reflected back at them in every table and
chart afterward. This is the concrete "mixed VN/EN in the same view" case
`AUDIT_PROMPT.md §2.3` asks to flag. Fix: extract the existing
`EDIT_DOC_TYPE_OPTIONS` label map into a shared `DOC_TYPE_LABEL` lookup
(mirroring `MODE_LABELS`'s pattern exactly) and use it at both display call
sites — 10-line change, no backend touch needed since `doc_type` values are
already stable enum strings.

**Finding P2-T3 (P3, effort S).** Department codes `PTSP`/`DP`/`DVA`
(`app/config/settings.py:319`) are never expanded to human-readable names
anywhere — not in the frontend, not in a backend comment, not in `CLAUDE.md`.
They appear as bare 2-3 letter codes in the upload form, the documents
table, and the Overview donut chart's legend. For a business user (the
audit's own persona: "would a new admin know what X means, or does jargon
leak into a business user's screen") these read exactly like the internal
engineering abbreviations the prompt asks to be rewritten — except here
it's business-org jargon rather than ML jargon, same effect: unexplained.
Fix: a small `DEPARTMENT_LABEL` map (even if the audit author can't supply
the correct expansions without insider knowledge — that's a one-time ask to
whoever owns the department list) shown as `"PTSP — Phát triển sản phẩm"`-style
pairs, matching the exact pattern the `doc_type` dropdowns already use.

**Positive finding — engineering jargon does NOT leak into the UI.** Explicitly
checked every visible label in `OverviewView.jsx`, `DocumentsView.jsx`,
`UsersView.jsx`, `ChatScreen.jsx`, `EmptyState.jsx`, `SourcePanel.jsx`, and
`login.html` for terms like "rerank", "coverage gate", "chunk", "embedding",
"RAG", "RRF", "retrieval" — none appear. "Chunk" is consistently rendered
as "đoạn" (segment), "retrieval" never surfaces as a word at all (folded
into "tìm kiếm"/"truy xuất" only in code comments, not UI text). This is a
real, verifiable strength worth calling out per the audit prompt's own
instruction to "tell me when something is already good."

### Empty / loading / error / success states

Systematically checked every async action:

| Action | Empty state | Loading state | Error state | Success confirmation |
|---|---|---|---|---|
| Chat: ask a question | `EmptyState.jsx` (greeting + prompt suggestions) — good | **Missing** — see Finding P2-J1 | `ChatScreen.jsx:141`, red text "Lỗi: {message}" — present but generic, no retry button | Implicit (answer renders); no distinct "done" signal beyond the streaming flag flipping off |
| Chat: refusal | See Finding P2-J3 — intended distinct state exists but is unreachable | n/a | n/a | n/a |
| Admin: Overview metrics load | `Empty` component per-panel (`OverviewView.jsx:56-58`), each chart has its own tailored empty copy ("Chưa đủ dữ liệu để vẽ biểu đồ theo ngày.", etc.) — thorough, panel-by-panel, genuinely good | No skeleton — page shows nothing until `fetchMetrics` resolves (`m &&` guard, `OverviewView.jsx:376`); brief blank page on slow network, `P3` | `Empty>Không tải được số liệu: {error}</Empty>` (`OverviewView.jsx:374`) — present | n/a (data just appears) |
| Admin: Documents list load | `emptyLabel="Chưa có tài liệu nào được nạp."` (`Table` default prop path) | No loading indicator at all while `fetchDocuments()` is in flight — table just shows nothing/stale until it resolves | `loadError` shown in the `Card`'s `hint` line (`DocumentsView.jsx:267`) | Toast-less; relies on the table simply updating after `load()` |
| Admin: Upload document | Dropzone shows filename once picked | Status line: *"Đang nạp... (có thể mất một lúc)"* — good, sets expectations | Red status text, real backend message surfaced (`err.message`) | Green status text with real counts (*"Đã nạp X (type) — N đoạn"*) — **this one is done well**, concrete and specific rather than a generic "Success!" |
| Admin: Edit document | n/a (always has a doc) | Status text, distinguishes rename (slow, warn-colored) from metadata-only (fast) — thoughtful | Red status text | Modal closes + table reloads; no lingering confirmation, acceptable for a fast operation |
| Admin: Delete document | n/a | No loading indicator on the row itself beyond the button's `disabled={deletingId === d.doc_id}` (present, subtle) | `window.alert()` — see P2-C1 | Row disappears from table on success |
| Admin: Users list load | `emptyLabel="Chưa có tài khoản nào."` | No loading indicator | `Không tải được danh sách: {error}` — present | n/a |

**Rollup: no screen has a genuine loading skeleton/spinner for its initial
data fetch** — every admin panel goes from blank to populated with no
intermediate state, and the chat composer's only "I heard you" signal is
the send button graying out. None of these are broken, but taken together
they're a consistent, fixable gap (`P2`, effort `S` each, `M` total across
the app) — a shared `<Spinner>`/skeleton pattern already implied by the
"vendored design system" convention (`CLAUDE.md`) would be the right single
place to add it once, then wire into each `useEffect` fetch.

### Destructive-action safety

**Finding P2-C1 (P2, effort S).** The admin console has a real `Modal`
component (`frontend/src/components/feedback/Modal.jsx`, used correctly for
"Edit document") but **delete confirmation bypasses it entirely** and uses
the browser's unstyled native dialogs: `window.confirm(...)`
(`DocumentsView.jsx:234`) and `window.alert(...)` on failure
(`DocumentsView.jsx:240`). Concretely wrong for a "must look like a
product, not a demo" bar: the confirm dialog is rendered by the OS/browser
chrome, ignores the app's theme (light/dark), ignores its type scale and
brand colors entirely, and — because it's synchronous/blocking — freezes
the whole tab while shown, which is a jarring interaction difference from
every other confirmation in the app. The copy itself is good (*"Xoá tài
liệu "{title}" khỏi hệ thống? Thao tác này không thể hoàn tác."* — specific,
names the document, states irreversibility) — only the presentation layer
is wrong. Fix: reuse `Modal` with a `variant="danger"` action button (the
`Button` component already supports a `variant="danger"` prop, used
elsewhere for the row-level "Xoá" button itself, `DocumentsView.jsx:299`) —
this is a drop-in swap, not a redesign.

There is no equivalent delete-user flow to audit (Users is read-only, see
§2.2), so this finding is scoped to documents only.

### Form validation, keyboard behaviour, focus management

- **Inline vs on-submit**: consistently **on-submit** across the app — the
  Upload form only reports "Chọn một tệp trước." after the user clicks
  "Nạp tài liệu" with no file chosen (`UploadCard.submit`, `DocumentsView.jsx:45-48`),
  and the Edit form only reports "Tên tài liệu không được để trống." after
  "Lưu" (`EditModal.save`, `DocumentsView.jsx:134-137`). This is at least
  *consistent* project-wide (not a mixed-pattern finding), just a `P3`
  opportunity to disable the submit button proactively instead of letting
  the click round-trip to a validation message.
- **Enter to submit**: works in the chat composer (`Composer.jsx:34-37`,
  Enter sends / Shift+Enter newlines, correctly guards
  `!e.nativeEvent.isComposing` so Vietnamese IME composition isn't
  interrupted — a real, non-obvious correctness detail done right), works in
  the Overview "Hỏi thử nhanh" input (`OverviewView.jsx:286-288`, same
  IME-safe pattern), and works natively in `login.html`'s real `<form>`
  (browser-default Enter-submits, no JS needed). **But it does NOT work
  inside `EditModal`'s text fields** (`DocumentsView.jsx:122-211`) — none of
  the three `Input`/`Select` fields there have an `onKeyDown` handler, so a
  user editing a document's title and pressing Enter does nothing; they
  must locate and click "Lưu". `P2` (real inconsistency the audit prompt
  explicitly asks to check for), effort `S` — one `onKeyDown` handler on the
  modal's outer `div`, guarded the same IME-safe way as `Composer.jsx`.
- **Esc to close modal**: confirmed **absent**. `Modal.jsx` (15 lines total)
  implements exactly one dismiss path — clicking the backdrop
  (`onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}`,
  `Modal.jsx:6`) — with **no `keydown` listener for `Escape`** anywhere in
  the component or in `EditModal`. `P2`, effort `S`: a `useEffect` adding a
  document-level `keydown` listener while `open` is true is a small,
  self-contained fix in the shared `Modal.jsx`, benefiting every future
  modal in the app at once.
- **Focus management after modal close**: confirmed absent — `Modal.jsx`
  has no focus trap (no initial-focus-on-open, no focus return to the
  triggering "Sửa" button on close, `role="dialog" aria-modal="true"` is
  present as a semantic hint but not backed by actual JS focus handling). A
  keyboard-only admin loses their place after every edit. `P2` (this is
  also a Phase 5 accessibility item; flagged here because it's squarely a
  "does the admin console feel finished" product question too), effort `M`
  (needs a real focus-trap implementation, not a one-liner, since it must
  also handle Tab-cycling within the modal).

### Does the admin console explain itself? Jargon check

Beyond the terminology table above: the console is largely honest about its
own limits rather than pretending to be more finished than it is — every
placeholder nav item (`Đánh giá chất lượng`, `Nhật ký`, `Mô hình`,
`Thiết lập`) shows real, specific, non-generic copy explaining exactly why
it's empty and where the real functionality currently lives instead
(`AdminShell.jsx:38-43`, `PLACEHOLDER_COPY`) — e.g. *"mô hình đang dùng
được đặt qua biến `CHAT_MODEL` trong .env"* names the actual mechanism. This
is a deliberately good pattern (explicitly commented as such in the source,
`AdminShell.jsx:9-12`: "every other item renders an honest placeholder
instead of the kit's fabricated pages") and stands in sharp, positive
contrast to a typical demo that ships fake "Coming soon" tiles. **Worth
protecting — do not replace this with generic "🚧 Coming soon" copy in a
future pass.**

No engineering jargon ("coverage gate", "rerank", "RRF", "embedding") leaks
into any label — reconfirmed here from the terminology-table pass above.
The one soft exception is the department-code and doc_type-enum leakage
already covered as P2-T2/P2-T3 — those are data-value leakage, not
label/jargon leakage, and are called out separately above.

---

## 2.4 Professionalism check

Framed as: would a Bảo Việt Life executive opening this cold see a finished
product? Evaluated from source (JSX/CSS/HTML) since no screenshots were
taken this phase — see the explicit visual-claim caveats inline.

- **Placeholder text / lorem ipsum / TODO in the UI**: none found.
  `grep -rniE "TODO|FIXME|lorem ipsum|xxx|coming soon"` across
  `frontend/src/**/*.{jsx,js}` (excluding legitimate `placeholder=` input
  hints) returned zero matches. `console.log`/`console.debug`/`console.warn`
  calls: zero matches anywhere in `frontend/src/`. This is a genuinely clean
  codebase on this axis — **confirmed absence, not just "didn't look."**
- **Broken images / default browser styling**: cannot be confirmed without
  a running browser + screenshot (Phase 3's job) — flagged explicitly as
  unverified rather than asserted. What IS verifiable from source: every
  `<img>` reference (`logo-baoviet-life-onnavy.png`, favicons) points at
  `/assets/...`, served by a real static mount (`app/main.py:213`,
  `app.mount("/assets", ...)`) — the files exist in
  `app/static/assets/` per the repo listing in `audit/00-system-map.md`
  (`app/static/assets/` present, `?? app/static/assets/` in `git status`).
  Not independently re-verified pixel-by-pixel here.
- **Page titles**: all three surfaces have distinct, correctly-formatted
  `<title>` tags — `Trợ lý AI Bảo Việt Life` (landing),
  `Trợ lý AI Bảo Việt Life — Quản trị` (admin),
  `Trợ lý AI Bảo Việt Life — Trò chuyện` (chat),
  plus `Đăng nhập — Trợ lý AI Bảo Việt Life` (login). Consistent brand name,
  clear em-dash suffix pattern, no raw file names or "React App" default
  titles anywhere. **Good.**
- **Loading/tab title while streaming**: **not implemented.**
  `grep -rn "document.title" frontend/src` returns zero matches — the
  browser tab title stays static (`"Trợ lý AI Bảo Việt Life — Trò chuyện"`)
  for the entire 25-60s a response streams in, unlike e.g. ChatGPT's
  animated/status tab title. A user who alt-tabs away during a long
  generation has no passive signal that the answer arrived. `P3`, effort
  `S` (a `useEffect` setting `document.title` while `busy` is true, reverted
  on completion).
- **Favicon**: consistent SVG + PNG favicon set
  (`/assets/favicon.svg`, `favicon-32x32.png`, `favicon-16x16.png`,
  `apple-touch-icon.png`) referenced identically across all four HTML
  entry points (landing, chat, admin, login) — checked each `<link
  rel="icon">` block, byte-identical paths in all four files. **Good,
  consistent.**
- **Branding — logo usage**: the Bảo Việt Life logo
  (`logo-baoviet-life-onnavy.png`) appears on the landing page header and
  the login page's navy rail, in both cases against the correct dark-navy
  background variant (the filename itself signals an "on-navy" asset
  chosen deliberately, not a generic logo forced onto a dark background
  where it might lose contrast) — consistent brand rail styling shared
  between `LandingScreen.jsx` and `login.html` (both use
  `linear-gradient(...var(--brand-navy)...var(--brand-ink)...)` — verified
  near-identical gradient stops in both files). The admin console and chat
  UI, by contrast, carry **no Bảo Việt logo image** at all — identity there
  is text-only ("Trợ lý AI Bảo Việt Life" in the sidebar) plus the abstract
  gold-triangle brand mark (`Triangle` component). This is a defensible,
  deliberate choice (a persistent large logo would eat vertical rail space
  in a dense, single-column app UI) rather than an inconsistency — noting
  it as a design decision to confirm with the design-system owner, not a
  defect.
- **Vietnamese copy quality**: read every user-facing string across
  `login.html`, `LandingScreen.jsx`, `EmptyState.jsx`, `Composer.jsx`,
  `ChatMessage.jsx`, all of `admin/*.jsx`. Tone is consistently formal,
  professional B2E register appropriate for an insurance company internal
  tool (no casual/internet-slang Vietnamese anywhere), diacritics are
  correct and complete throughout (spot-checked long strings like
  *"Đổi tên sẽ nạp lại tài liệu từ tệp gốc để tìm kiếm bám đúng tên mới"* —
  grammatically sound, no dropped tone marks), no truncation artifacts
  (`text-overflow: ellipsis` is used deliberately with `title=` tooltips
  backing the full string, e.g. `DocumentsView.jsx` table cells,
  `BarList`/`Donut` labels in `OverviewView.jsx` — not just silently cut
  off). Nothing reads as machine-translated — sentence structure is
  natural, not English-word-order-with-Vietnamese-vocabulary (a classic
  MT tell that's absent here). **This is a real strength; the two
  terminology gaps (P2-T2, P2-T3) are the only defects found in an
  otherwise careful, native-quality copy pass.**
- **Console noise**: cannot verify without a live browser session (Phase 3).
  Source-level check (no `console.*` calls) is necessary but not sufficient
  — a library dependency (React, KaTeX) could still warn at runtime; flagged
  as unverified rather than asserted clean.

---

## Findings summary (this phase only)

| ID | Severity | Effort | File:line | Finding |
|---|---|---|---|---|
| P2-J1 | P2 | S | `frontend/src/chat/ChatScreen.jsx:49`, `ChatMessage.jsx:129` | No loading affordance during 25-60s wait for first token |
| P2-J2 | P2 | S | `frontend/src/chat/ChatMessage.jsx:7-62` | Citation chips render for sources never inline-cited in the answer text |
| P2-J2b | — | — | `frontend/src/chat/ChatScreen.jsx:25` | Refresh loses the conversation (see §2.2 "No conversation persistence" for the full writeup + fix) |
| P2-J3 | P2 | S | `frontend/src/chat/ChatMessage.jsx:5,116`; `app/query_timing.py:79-86` | `isRefusal` check is always false in production (timing footer breaks exact-match) — the friendlier refusal UI + recovery suggestion never shows |
| P2-J6 | P1 | M | `app/api/login.py` (full file), `app/accounts.py` (full file), `scripts/seed_accounts.py` | No self-service password reset/change, no forced first-login change, no deactivation — entire account lifecycle is a server-shell operation |
| P2-F1 | P1 | S–M | `frontend/src/chat/ChatScreen.jsx:25` | No conversation persistence — smallest fix is `sessionStorage`, not full server-side history |
| P2-F2 | P1 | M | `frontend/src/chat/ChatMessage.jsx:64-86` | No feedback/flag-wrong-answer loop anywhere |
| P2-F3 | P2 | M | `frontend/src/components/data/Table.jsx`, `frontend/src/admin/DocumentsView.jsx`, `app/api/ingest.py:264-269` | No search/filter/sort/pagination in documents table; no server-side pagination in `GET /documents` |
| P2-T1 | P2 | S | `frontend/src/admin/UsersView.jsx:24` | Copy inaccurately describes accounts as admin-page-only ("trang quản trị") when most are chat-only employee accounts |
| P2-T2 | P2 | S | `frontend/src/admin/DocumentsView.jsx:288,443`, `OverviewView.jsx:5` | `doc_type` shown as raw English enum in tables/charts while its own input dropdown is bilingual — mixed VN/EN in the same view |
| P2-T3 | P3 | S | `app/config/settings.py:318-319`, `DocumentsView.jsx` department select/table | Department codes (PTSP/DP/DVA) never expanded anywhere in the codebase |
| P2-C1 | P2 | S | `frontend/src/admin/DocumentsView.jsx:234,240` | Delete confirmation uses native `window.confirm`/`alert` instead of the app's own `Modal` component |
| P2-C2 | P2 | S | `frontend/src/admin/DocumentsView.jsx:122-211` (`EditModal`) | Enter does not submit the Edit-document form, inconsistent with Composer/AskPanel |
| P2-C3 | P2 | S | `frontend/src/components/feedback/Modal.jsx` | No Esc-to-close handler on the shared Modal component |
| P2-C4 | P2 | M | `frontend/src/components/feedback/Modal.jsx` | No focus trap / no focus return after modal close |
| P2-P1 | P3 | S | `frontend/src/chat/*` (no `document.title` usage) | Browser tab title never reflects streaming/loading state |

Positive findings worth explicit protection (per `AUDIT_PROMPT.md`'s
"tell me when something is already good" instruction):

- Zero engineering jargon ("rerank", "coverage gate", "chunk", "RAG") leaks
  into any UI label — every occurrence is translated to a plain-language
  Vietnamese business term.
- `OverviewView.jsx`'s admin dashboard is a genuinely complete, well-chosen
  set of panels that actually answers "is the system healthy" — the
  strongest single screen audited in this phase.
- Honest, specific placeholder copy for unbuilt admin nav sections instead
  of generic "coming soon" tiles.
- Vietnamese copy quality is native-register throughout, zero
  machine-translation tells, complete and correct diacritics.
- IME-composition-safe Enter-to-send handling in the chat composer and
  quick-ask panel (a real, easy-to-miss Vietnamese-input correctness
  detail, done right in both places it matters).
- RBAC page-redirect and endpoint-level guards are real and server-enforced
  (re-verified live in this phase with both demo accounts — every
  admin-scoped endpoint tested returned a correct `403` for the employee
  account, not just a hidden button).

## Unverified suspicions — needs a follow-up run

- The `refusal_rate`/`mode_breakdown.refusal` metric showing `0` immediately
  after a live-verified textbook refusal (Journey 5, #2) — could not
  root-cause in this read-only phase without directly reading
  `logs/query_timings.jsonl` and correlating timestamps. Confirm with:
  `tail -5 logs/query_timings.jsonl | python3 -m json.tool` right after
  reproducing the refusal, checking the `mode`/`coverage_gate_outcome`
  fields the log actually recorded for that request.
- Console errors/warnings on any of the three surfaces — needs Phase 3's
  live browser session; not assessable from source alone.
- Broken images / actual rendered visual quality — same, needs Phase 3
  screenshots.
