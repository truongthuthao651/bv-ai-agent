# Phase 3 — Frontend: visual design, theming, components

Date: 2026-08-08. All findings verified against the **running app** (server already up at
`http://127.0.0.1:8000`, Ollama/Qdrant up) via a headless-Chrome + CDP screenshot harness
(`Emulation.setDeviceMetricsOverride` for viewport, `Emulation.setEmulatedMedia` for
`prefers-color-scheme`, real session cookies for the two demo accounts). 19 screenshots in
`audit/screenshots/{screen}-{viewport}-{theme}-{state}.png`. Read-only phase — no edits made,
no rebuild run (bundle unchanged since 2026-08-07 22:42, confirmed via `git status` showing no
`frontend/src` changes in the dirty tree).

**Not screenshotted**: `frontend/src/showcase/` — confirmed via `frontend/vite.config.js`
`rollupOptions.input` (only `landing`, `admin`, `chat` are build entries) that the component
showcase is **not part of the deployed `dist/` bundle at all**. It's a dev-only tool
(`npm run dev` territory), unreachable in production. Not a bug — just out of scope for a
production visual audit; noted so nobody goes looking for `/showcase` in prod.

## 3.1–3.2 Setup, tokens & consistency

**Finding F3-1 (P1, M): The landing page never themes — dark mode does nothing there — because it bypasses the token system with hardcoded hex, unlike every other screen.**
- Evidence: `audit/screenshots/landing-desktop-light-default.png` and
  `landing-desktop-dark-default.png` are **byte-identical** (both 1,548,869 bytes) despite one
  being captured with `prefers-color-scheme: dark` emulated and the other `light`. Compare with
  `chat-desktop-light-empty.png` vs `chat-desktop-dark-empty.png` (172,381 vs 166,824 bytes,
  visibly different — chat and admin both theme correctly).
- Root cause, `frontend/src/landing/LandingScreen.jsx:15-17,43,67`: `const INK =
  "var(--brand-ink)"` is fine, but line 17 hardcodes `heading: "#FFFFFF"`, line 43 hardcodes
  `#06192B` inline in a gradient, line 67 hardcodes `color: "#fff"`. None of these read
  `data-theme` — the page is permanently locked to one hand-picked navy palette. There is also
  no `<ThemeToggle>` rendered on the landing page at all (confirmed absent in both screenshots),
  so a visitor has no way to know theming exists until they log in.
- Impact: this may well be an intentional choice (a marketing hero page in fixed brand navy is
  a legitimate design), but as shipped it's **undocumented and inconsistent** — chat and admin
  both respect the OS preference and a manual toggle, landing silently doesn't, and there's
  nothing in the code (no comment, no design-doc reference) confirming this is deliberate versus
  simply the token migration not reaching this one file.
- Fix: either (a) confirm intentional and add a one-line comment explaining why landing is
  theme-locked, or (b) replace the 4 hardcoded hex values with `var(--text-on-accent)` /
  `var(--brand-ink)` equivalents so it themes like everything else. Effort: S once the decision
  is made.

**Finding F3-2 (P3, S): `npm run lint`'s hex/px enforcement rule is silently disabled** —
inherited from Phase 0 (`audit/00-system-map.md` §0.1): oxlint's `no-restricted-syntax` rule
(the one that would have caught F3-1's hardcoded hex at commit time) is dropped from the
generated config because oxlint can't execute it, and `npm run lint` prints a warning but still
exits 0. A "clean lint" result on this repo does not mean token-compliant. Fix: either find an
oxlint-compatible way to flag raw hex/px in `style={{}}` objects, or add a one-line pre-commit
grep (`grep -rnE '#[0-9a-fA-F]{3,8}' frontend/src --include=*.jsx | grep -v /tokens/`) as a
stopgap so the gap doesn't silently widen further — grep results at audit time (all defensible,
see below) show only **5 files** with hardcoded hex outside `tokens/`: `LandingScreen.jsx` (4
occurrences, F3-1), `Sidebar.jsx:70`, `AdminShell.jsx:212`, `Button.jsx:23`, `Badge.jsx:7` — the
latter four are all `color: "#fff"` text-on-a-colored-avatar/badge, which is defensible (white
text on a fixed brand-navy avatar chip doesn't need to theme) but should still route through
`var(--text-on-accent)` for consistency's sake since that token exists precisely for this case.

**Design-token discipline otherwise looks good**: `frontend/src/tokens/colors.css` defines a
real semantic scale (bg/surface/border/text-primary/secondary/muted, full dark variant, chart
series colors, legacy aliases indirected onto the same tokens) and it's used almost everywhere
via `var(--...)` in inline styles — the 5-file exception list above is short for a 34-component
frontend. No raw `px` spacing found outside the token scale except two identical
`max-width: 640px` values in `frontend/src/chat/ChatScreen.jsx:12,14` (a magic number that should
probably be `var(--content-max)`, which the codebase already defines and uses two lines away at
`ChatScreen.jsx:121` — pick one).

## 3.3 Color & theming

**Finding F3-3 (P1, M) — CONFIRMED, quantified: `--text-muted` fails WCAG AA contrast in LIGHT
mode (the opposite of the usual "dark mode is the afterthought" pattern).**
- Computed (WCAG 2.1 relative-luminance formula) from the actual token values in
  `frontend/src/tokens/colors.css:12`: `--text-muted: #8CA0B3` on `--bg: #F7F9FC` (light theme)
  = **2.58:1** — fails both normal text (4.5:1) and large text (3:1) thresholds.
- The dark-theme equivalent, `--text-muted: #7C90A5` on `--bg: #0D1620`
  (`colors.css:26`) = **5.54:1** — passes AA comfortably. So this is specifically a light-mode
  regression, not a generic "dark mode wasn't finished" issue.
- `--text-secondary` is fine in both themes (light: `#5A6B7F` on `#F7F9FC` = 5.18:1; passes).
- Where it's visible: every muted caption in the admin console (card subtitles like "Số lần tài
  liệu được trích dẫn trong câu trả lời" in `admin-overview-desktop-light-full.png`), composer
  placeholder text ("Hỏi về một quy tắc, quy trình, hoặc công thức…" in
  `chat-desktop-light-empty.png`), and KPI card labels — all visibly low-contrast gray-on-near-
  white in the light-theme screenshots, consistent with the computed ratio.
- Fix (S effort, one-line token change): darken `--text-muted` in the light theme — e.g. `#6E8296`
  gets to ~3.9:1 (still short), `#5F7488` gets to ~4.6:1 (passes). Recommend picking a value and
  re-checking against `--surface` (`#FFFFFF`) too since muted text also sits on cards, not just
  `--bg`.

**Theme mechanics** (`frontend/src/theme/useTheme.js`): correctly defaults to
`prefers-color-scheme` on first visit (`systemTheme()`), persists an explicit choice to
`localStorage["bv-theme"]`, and live-updates on OS theme change only while no explicit choice is
stored (`localStorage.getItem(STORAGE_KEY)` guard at line 24) — this is the right behavior
(don't fight a user's manual override). Applies via `data-theme` on `document.documentElement`,
which the CDP emulation test confirms actually renders both themes correctly for chat and admin
(F3-1 is the one screen that opts out). No flash-of-wrong-theme was observed in these screenshots
(theme is read synchronously in `initialTheme()` before first paint), but this harness can't
detect a sub-100ms flash — worth a manual check with DevTools' "Emulate CSS media" toggled
mid-session if it matters later.

## 3.4–3.5 Components, tables & charts

**Finding F3-4 (P1, M): the admin console has ZERO responsive layout — the left rail never
collapses, unlike chat which already has a working pattern for this exact problem in the same
codebase.**
- Evidence: `audit/screenshots/admin-overview-mobile-light-full.png` (375px viewport) — the
  264px-wide nav rail eats 70% of the screen, KPI card labels truncate to `Số ...`, `Tài...`,
  `Tỷ ...`, `Độ...`, `Số ...` (unreadable), and the same truncation is still visible at
  **768px tablet** (`admin-overview-tablet-light-full.png`) — the 5-column KPI grid doesn't
  reflow at either breakpoint.
- Root cause, `frontend/src/admin/AdminShell.jsx:156`: `width: "var(--rail-width)"` (264px,
  `frontend/src/tokens/spacing.css:19`) is applied unconditionally — no media query, no JS
  breakpoint check, no collapse-to-drawer behavior anywhere in the file.
- The fix already exists in this repo and just needs to be ported: `frontend/src/chat/
  ChatScreen.jsx:10-19` implements `useIsMobile()` (a `matchMedia("(max-width: 640px)")` hook)
  and conditionally renders the sidebar as a slide-over drawer with a hamburger button
  (`ChatScreen.jsx:91-106`) instead of a fixed rail below that breakpoint — confirmed working
  correctly in `audit/screenshots/chat-mobile-light-empty.png`. Admin has no equivalent.
- Second root cause, `frontend/src/admin/OverviewView.jsx:378`:
  `gridTemplateColumns: "repeat(5, 1fr)"` for the 5 KPI cards is also unconditional — even once
  the rail is fixed, this grid still needs a `repeat(auto-fit, minmax(...))` or a breakpoint-based
  column count to avoid re-truncating on any viewport under roughly 1100px of content width.
- Effort: M — this is the single highest-value visual fix in the whole audit (every admin screen
  inherits it) and the pattern to copy is already written and tested elsewhere in the same repo.

**Overview dashboard charts** (`admin-overview-desktop-light-full.png` /
`OverviewView.jsx`): mostly real, not "numbers in boxes" — there's a genuine day-bucketed bar
chart, an hour×weekday heatmap ("Thời điểm hỏi nhiều"), and horizontal bar lists for top-cited
documents, all correctly empty-stated ("Chưa đủ dữ liệu để vẽ biểu đồ theo ngày") rather than
showing a broken/blank chart. Two exceptions worth a second look:
  - "Tài liệu theo phòng ban" (documents by department) renders a donut that is **100% one slice
    labeled "Không đặt"** (department not set) — because no document in the synthetic corpus has
    a department tag. As implemented this chart cannot show anything else until department
    tagging is actually used, so it's currently dead weight on the dashboard rather than a real
    KPI — worth hiding until ≥1 document has a department, or relabeling the empty state
    explicitly ("Chưa gắn phòng ban cho tài liệu nào") instead of rendering a 100% pie of nothing.
  - "Chế độ trả lời" (answer mode breakdown) renders as a single badge ("Có căn cứ: 4"), not a
    chart — with only one mode observed in the sample window this reads fine, but confirm it
    becomes an actual distribution (badges or a bar) once advisory/general-knowledge modes are
    also exercised, since a single static badge doesn't scale to 3 categories.
  - **Latency number surfaced to the admin**: "Độ trễ trung vị (p50): 39.7s" — real, measured,
    and consistent with Phase 4's live findings (see `audit/04-chatbot.md`) — flagging here only
    because a 40-second median response time is the kind of number that should be impossible to
    miss on this dashboard, and it currently sits as one KPI card among five with no visual
    emphasis (no color-coding, no threshold/target line) despite arguably being the most
    important number on the page.

**Login page** (`app/templates/login.html`, screenshotted separately since it's a plain Jinja
template, not part of the Vite build): clean, on-brand, no complaints — two-column
navy-hero/white-form layout, correct dark-mode rendering (`login-desktop-dark-default.png`),
readable at mobile width. The one thing worth confirming later (not verifiable via screenshot
alone) is `<label>`/`for` wiring and focus order — deferred to Phase 5's accessibility pass.

## 3.6 Motion, polish & performance

**Bundle size — good, not a concern.** `app/static/dist/` totals **1.7MB** uncompressed. Largest
chunks: `chat-hZ0NUc2z.js` 272KB, `jsx-runtime-Dgo-PerU.js` 188KB (shared React runtime),
`admin-DN3SolIi.js` 40KB, `chat-DYaBz7da.css` 32KB, `landing-CmXXkt2s.js` 8KB. KaTeX's own CSS
is pulled in by `chat/ChatScreen.jsx:2` (`import "katex/dist/katex.min.css"`) rather than a
separate lazy chunk — at this total size it's not worth the complexity of lazy-loading it.

**Console**: zero errors/warnings/exceptions captured via CDP `Runtime.consoleAPICalled` /
`Runtime.exceptionThrown` / `Log.entryAdded` during a fresh load-and-settle (3s) of both
`/chat/` (as employee) and `/admin/#overview` (as admin) — genuinely clean.

**RBAC redirect — re-verified correctly, one methodology note.** An early screenshot attempt
(same URL, switching cookies between shots in one Chrome profile) appeared to show an employee
reaching the full `/admin/` shell instead of being redirected — this turned out to be **Chrome's
disk cache serving a stale prior response**, not a real bug: `curl -b <employee cookies> -H
"Accept: text/html" http://127.0.0.1:8000/admin/` returns a clean `303 See Other` →
`location: /chat/`, and a retake with `Network.setCacheDisabled` + `Network.clearBrowserCookies`
before navigation shows the correct redirect
(`audit/screenshots/admin-as-employee-redirect-check.png` — employee lands on the `/chat/` empty
state, not `/admin/`). Noted here so nobody re-discovers this as a false P0 from a screenshot
alone — the curl evidence is authoritative.

**Not evaluated in this phase** (needs interaction, not a static screenshot): focus-visible
states, keyboard traps in the (nonexistent, per code read) modal, `prefers-reduced-motion`
handling, and streaming-message layout shift — these belong to Phase 4 (live chat) and Phase 5
(accessibility) respectively and are deliberately left to those phases rather than guessed at
here.
