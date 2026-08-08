# Prompt: apply the Bao Viet Life design system to the real app

Run from `/Users/haphan/Desktop/bv-ai-agent/bv-ai-agent` (the app repo).

---

Rebuild this app's entire UI so it matches the Bao Viet Life design system exactly:
landing page, auth, admin console, and chat, on one shared token and component layer.

## 0. Read before writing anything

**Design system (source of truth, treat as read-only):** `/Users/haphan/Desktop/bv-ai-agent/`
— the local export of design system `a2e08d`, namespace `BaoVietLifeDesignSystem_a2e08d`.

Read in this order, completely:
1. `readme.md` — the whole thing. It states the design direction, the palette
   discipline, the elevation ladder, the content rules, and a Caveats section that
   tells you which parts are proposals rather than settled decisions. Do not skip it.
2. `styles.css` and `tokens/` — `colors.css`, `typography.css`, `spacing.css`,
   `radii-shadows.css`, `fonts.css`.
3. `components/` — Button, Badge/Tag, Input/Select/Textarea/Dropzone, Card, Modal,
   Table/StatTile, ChatBubble, ChatComposer, PromptSuggestion, KpiCard, StatusPill,
   ThemeToggle. Each has a `.prompt.md` and `.d.ts` next to it; read those for the
   intended API before you use a component.
4. `ui_kits/landing/`, `ui_kits/chatbot/`, `ui_kits/admin-dashboard/` and their READMEs.
5. `guidelines/*.html` — foundation specimens (brand colors, light/dark tokens,
   semantic colors, type scale, type family, spacing, spacing-in-use, radii, logo,
   header treatment). Open them in a browser, don't just read the markup.
6. `screenshots/*-v2.png` — the intended result. Match what you see.
7. `_ds_manifest.json` and `_adherence.oxlintrc.json` — the component inventory and
   the boundaries lint.

**App (what you change):** this repo. Read `CLAUDE.md`, then `app/main.py`,
`app/auth.py`, `app/api/*.py`, `app/static/index.html`, `app/templates/login.html`,
`scripts/open_webui/`, and `.env.example`.

## 1. Security — non-negotiable, and one hard stop

These bind everything below and nothing in this prompt relaxes them:

- **Never read, open, list, or reference anything under `data/real/`.** Development
  and testing use `data/synthetic/` only.
- **No real document content, names, policy numbers, or amounts** in code, tests,
  fixtures, logs, commit messages, or docs.
- **No telemetry, no analytics, ever.** Not even self-hosted.
- **No outbound network calls at runtime.** See §2.
- Do not weaken, bypass, or "temporarily" disable `app/auth.py`, its
  `PUBLIC_PREFIXES`, or the `_PUBLIC_DOC_RE` allowlist. If a screen you are building
  seems to need that, stop and tell me instead.

### HARD STOP before any chat work

`app/auth.py` documents the current model precisely: port 8000 is meant to be
loopback-only (`API_HOST=127.0.0.1`), gated by one shared `ADMIN_PASSWORD` for a
single manager, while the **employee-facing auth is Open WebUI's `WEBUI_AUTH`**.
`PUBLIC_PREFIXES` deliberately exempts `/v1`, and the file's own comment (SEC1)
warns that anyone who can reach the API host on the network can call
`/v1/chat/completions` directly, bypassing Open WebUI entirely.

Serving an employee chat UI from port 8000 therefore changes this app from
"loopback admin tool" to "network-reachable multi-user product", and the existing
auth does not cover that. Before you write a line of Phase 4:

1. Write me a short security note covering: what `API_HOST` has to become, who can
   then reach `/v1`, whether `API_SHARED_SECRET` is now mandatory rather than opt-in,
   what authenticates an individual employee at `/chat`, and what a per-user session
   would require (there is no user store today — no database, no signup).
2. Propose the smallest change that keeps employee access no weaker than today's
   `WEBUI_AUTH`. A single shared password for the whole company is not an acceptable
   answer for an employee surface; say so if that is where the analysis lands.
3. **Wait for my approval.** Do not build `/chat` before I have read that note.

Phases 0–3 do not touch this and can proceed normally.

## 2. Other hard constraints

**Vietnamese UI chrome stays.** The kits use English chrome; this is the one place
you deliberately diverge. Take the *visual* layer — palette, type scale, spacing grid,
radii, shadow/elevation ladder, layout, dark theme, bento grid, chart language,
motion — and keep every existing Vietnamese label verbatim. New surfaces need new
Vietnamese copy in the same direct, procedural voice as today's screens: no marketing
hype, plain language over jargon, retrieval terms ("chunk", "embedding") only in
tooltips or advanced sections. Translate the kit's English strings; do not paste them.

**Fully offline. No CDN, no runtime network.** This does not bend. The kits load
React, ReactDOM, and Babel from unpkg, and `tokens/fonts.css` imports Inter from
Google Fonts — every page load would then reach a third party from inside a regulated
insurer's network, leaking IP, user-agent, and referrer. That is squarely the
no-telemetry rule, and the deployment machines may be air-gapped outright.
- Self-host Inter as woff2 in `app/static/fonts/` with a `@font-face` block and the
  system-stack fallback already in `--font-sans`. Subset must include full Vietnamese
  diacritics. If you cannot obtain the files offline, stop and tell me — do not fall
  back to the CDN import or silently to system fonts.
- Self-host KaTeX (CSS + fonts) for math rendering.
- Charts in the kit are hand-rolled inline SVG. Keep them that way; add no chart library.
- Verify with devtools offline mode, per screen, and say that you did.

**A build step is allowed — on the dev machine only.** CLAUDE.md's no-build posture is
about the *deployment* machine (company policy: no Docker, native venvs). That stays
true: the deployment machine must need nothing but Python and the existing venvs, and
must never run npm.
- Scaffold `frontend/` (Vite + React) at the repo root, building to `app/static/dist/`,
  and **commit the build output**, so deploying stays `git pull` + restart.
- The point of allowing this: use the design system's `components/*/*.jsx` and
  `ui_kits/*/*.jsx` close to verbatim rather than hand-translating them. Copy them in
  and adapt them to real data and Vietnamese copy. Every hand-rewrite is a place the
  design drifts — fidelity to the kit is the goal.
- **Node is not installed on this machine.** If that is still true when you start,
  say so and stop. Do not improvise a workaround.
- Supply chain, since npm is new here: minimal deps (react, react-dom, vite,
  @vitejs/plugin-react, katex — justify anything else), exact pinned versions,
  `package-lock.json` committed, everything but react/react-dom/katex as
  `devDependencies`. Nothing from npm executes on the deployment machine.

**No fabricated data in production UI.** The kits ship fixed demo data. Every panel
either binds to real data or does not ship. See §8.

## 3. Brand and assets

Copy `assets/logo-baoviet-life.webp` and `assets/logo-baoviet-life-onnavy.png` into
`app/static/assets/`. Rules from the design system's readme, which you must follow:

- The official lockup is the logo. **On navy surfaces use the `-onnavy` variant** —
  the wordmark and tagline reverse to white while the globe and the V wedge keep
  their gold. **Never flatten the whole mark to white with a CSS filter.**
- The recurring brand motif is a small **gold triangle** echoing the logo's "V"
  (`Triangle` in `ui_kits/landing/LandingScreen.jsx`). Reuse that component; do not
  redraw it per screen.
- Gold is an accent at roughly 5–10% of surface area — active nav, KPI highlights,
  the triangle, one hero element per screen. **Never gold text on white.**
- **No third-party icon set.** Plain geometric shapes (dots for status, the gold
  triangle) and short text labels, matching the real product's icon-free convention.
  Do not add lucide, heroicons, feather, or any icon package.
- **No emoji** in UI chrome. Functional glyphs only (✓, ↑, ▾, ✕, →) where they
  replace an icon. Note that today's Open WebUI ingest pipe is literally named
  "📥 Nạp tài liệu" — leave that string alone, it is a model name in Open WebUI's
  own dropdown, not our chrome.
- **Favicon and app icons:** replace the generated "BV" mark with one derived from
  the real lockup, in the current palette. Ship the usual sizes plus an SVG, and set
  `theme-color` per theme.
- Backgrounds are flat color. No photography, patterns, or gradients — the two
  exceptions are the navy landing/auth diagonal and the blur permitted on floating
  surfaces (composer, dropdowns).

**Palette drift to fix:** `scripts/open_webui/apply_branding.py` hardcodes the *old*
palette (`BV_BLUE = #0072bc`, `BV_GOLD = #f7b928`, navy `#003a63`), as do
`app/static/index.html` and `app/templates/login.html`. The design system's brand
values are now `--brand-blue #2A7AC1`, `--brand-navy #14456F`, `--brand-ink #0C2A45`,
`--brand-gold #E0A208`. Everything must land on the new values — see §10 for Open WebUI.

## 4. The design contract

Check your work against this list on every screen. Details are in `readme.md` and the
`guidelines/` specimens; this is the summary you will be reviewed against.

- **Never use a raw hex in component code.** `--brand-*` are raw values that exist to
  feed the semantic tokens; UI code uses the semantic layer (`--bg`, `--surface`,
  `--surface-raised`, `--surface-sunken`, `--border`, `--border-strong`, `--hover`,
  `--active`, `--text-primary/secondary/muted`, `--text-on-accent`, `--text-on-gold`,
  `--accent*`, `--gold*`, `--success/warning/danger` + `-subtle`, `--focus-ring`,
  `--chart-*`). The one sanctioned exception is the navy marketing surface, which sits
  outside the theme ladder and carries its own literals — see `INK`/`onInk` in
  `LandingScreen.jsx`. Reuse those constants, don't invent new ones.
- **Elevation is a lightness ladder, in both themes:** `--bg` canvas → `--surface`
  cards → `--surface-raised` + shadow for floating things (composer, dropdowns,
  tooltips), with `--surface-sunken` for wells, input tracks, and chart tracks — the
  only surface that goes *down*. Depth comes from soft large shadows, not 1px grey
  lines; a hairline border ships alongside the shadow for crispness but is never the
  primary separator.
- **Dark is not an inversion.** Everything resolves through `data-theme="light"|"dark"`.
  Never hand-write a dark override that bypasses a token.
- **Type:** Inter, whole-pixel scale only — 11/12/13/14/16/18/20/24/30/38. 11–14 is the
  UI range, 16+ is content and headings. **Body leading never below 1.5**, because
  Vietnamese stacked diacritics clip at tighter values. Tabular numerals on every
  metric (`--tabular-nums`).
- **Spacing:** one 4px grid, `--space-N` = N×4px. Use the layout constants rather than
  re-deciding per component: `--pad-control-y/x`, `--pad-cell-y/x`, `--pad-card` 20,
  `--pad-card-lg` 24, `--pad-page` 32, `--gap-tight` 8, `--gap-card` 16,
  `--gap-section` 32, `--rail-width` 264, `--panel-width` 360, `--content-max` 768,
  `--control-h-sm/md/lg` 32/36/44 so every control in a row aligns.
- **Radii:** 6–8px controls, 12–16px cards and modals, full pill on status and
  composer elements.
- **Motion:** hover lift and color shift only, `--motion-fast` / `--motion-normal`,
  no bounce. Respect `prefers-reduced-motion`.
- **Charts:** one shared language enforced by a single `Panel` wrapper — same padding,
  same header (title + a plain-language line saying what the chart shows), same grid
  weight (`--chart-grid`), same track (`--chart-track`). `--chart-series-a` (blue) is
  always the primary series; `-b` (gold) is only ever the highlighted or comparison
  one; `-c`/`-d` are third and fourth categories, never emphasis.
- **Copy:** label metrics in the reader's terms. The kit says "Questions today",
  "People using it", "Typical answer time", "Most-used documents" — not "queries",
  "p50 latency", "top-cited chunks". Carry that discipline into Vietnamese. Every card
  gets a one-line plain-language hint. Deltas know which way is good (`betterWhen`),
  so falling answer time reads green and falling helpfulness reads red.
- **Long Vietnamese strings:** content runs 20–30% longer than English. Tables, chips,
  and buttons must give that room. Long document names truncate with an ellipsis and
  carry the full name in `title`, never wrap inside a pill.

## 5. Phase 0 — foundation

1. Scaffold `frontend/` (Vite + React, pinned, output `app/static/dist/`).
2. Vendor `styles.css` + `tokens/*.css` in, with the Google Fonts import replaced by
   self-hosted `@font-face`. Keep the legacy alias block at the bottom of `colors.css`
   — existing markup references those names and the aliases are what make it
   dark-theme-aware for free.
3. Copy the component library in from `components/` and keep the exported names and
   APIs. Wire `_adherence.oxlintrc.json` into the frontend lint config and keep it
   passing.
4. Theme switching: `data-theme` on `<html>`, persisted to localStorage, defaulting to
   `prefers-color-scheme`, no flash of wrong theme on load. Port `ThemeToggle`.
5. Copy brand assets per §3 and build the favicon set.

**Deliverable:** one throwaway page rendering every component in every variant, in both
themes, plus the type scale, spacing scale, and color tokens. Show it to me, and
confirm it loads with the network disabled. Stop here.

## 6. Phase 1 — landing page (new surface)

Port `ui_kits/landing/LandingScreen.jsx`: navy diagonal (`--brand-navy` → `INK` →
`#06192B`), logo top-left in the `-onnavy` variant, "Internal tool · BV AI Agent"
pill with the gold triangle, the 62px hero headline, the gold `Start →` CTA with its
lifted shadow, a secondary "I already have an account", the three value props over a
hairline rule, and the footer with the green status dot and "Internal use only".

Translate all of it to Vietnamese. The three value props map onto claims this product
genuinely makes — answers cite the source document and page, full Vietnamese and
actuarial terminology, nothing leaves the internal network — so keep their substance
and check each is still true of the shipped system before you write it.

Serve it as the public entry point. Where its two CTAs go depends on §7, so wire them
last.

## 7. Phase 2 — auth

Read the design system readme's caveat on this before starting: the landing/auth kit
is **a proposal, not a mirror of today's auth**. `app/auth.py` has no user store, no
signup, and one shared `ADMIN_PASSWORD`; `AuthScreens.jsx` assumes per-employee
accounts with department-admin approval.

So, in order:
- **Build now:** the `AuthShell` chrome from `AuthScreens.jsx` — navy brand rail with
  logo, "The policy library, answerable." headline, the three promise lines with gold
  triangles, and the light form panel — restyling the real
  `app/templates/login.html` inside it. Keep this a plain Jinja template, not the
  React bundle; it is a pre-auth page and does not need it. Keep the real single-password
  flow from `app/api/login.py` and `app/auth.py` exactly as it is.
- **Do not build:** the Create-account tab, the department select, the password-strength
  rule, "Keep me signed in", "Forgot password?", or the request-sent confirmation.
  Every one of those implies a user store that does not exist. Drop the tab strip and
  render sign-in alone.
- **Tell me** what a per-employee account model would take, and what the alternative in
  the readme — a single "Sign in with your Bảo Việt account" SSO button, no signup —
  would take instead. This decision gates the landing CTAs and Phase 4. I will answer.

Note for accuracy: `AuthScreens.jsx` lists departments `PTSP`, `DP`, `DVA` and its own
comment names `settings.departments` in `app/config/settings.py` as the source of
truth, validated by `_validate_department()` in `app/api/ingest.py`. Anywhere a
department appears, read it from settings — never hardcode the list, and always submit
the bare code, with any gloss as display only.

## 8. Phase 3 — admin console

Rebuild `app/static/index.html` as React under `frontend/src/admin/`, adapting
`AdminShell.jsx`, `OverviewView.jsx`, and `DocumentsView.jsx` rather than
reimplementing them. Update the `StaticFiles` mount in `app/main.py`; keep `/` as the
admin entry point. Delete the old file only once the replacement is verified — not before.

**Shell:** sidebar nav grouped exactly as the kit has it — Monitor (Overview,
Evaluation, Logs) / Content (Documents, Users) / Configure (Models, Settings) — with
theme toggle and user block in the header. Only Overview and Documents are real; the
rest render an honest Vietnamese placeholder saying the section is not built yet.
Do not fake them. The ⌘K search in the kit's header is a visual affordance with no
overlay behind it: either implement it against the documents list or leave it out
entirely — do not ship a key hint that does nothing.

**Behavior that must survive with identical semantics and endpoints.** Read today's
inline `<script>` carefully and carry over every fetch, error path, and `escapeHtml`
call — this is a visual rebuild, not a behavior rewrite:
- document upload → `POST /ingest`, including the doc-type and department selects
- documents list, edit, delete → `GET`/`PATCH`/`DELETE /documents`, including the
  rename note and source-URL field
- metrics with the window selector → `GET /metrics/summary`
- the ad-hoc ask box
- Ollama and Qdrant health badges → `GET /health`
- logout → `POST /logout`

Keep XSS-safe escaping on every interpolated document field. React escapes by default;
anywhere you reach for `dangerouslySetInnerHTML`, don't.

**Documents view:** dropzone, table with ingestion stepper, failed-parse recovery, and
the detail modal, per `DocumentsView.jsx`. The accepted extensions must match today's
input (`.md,.docx,.yaml,.yml,.pdf,.xlsx,.xls,.png,.jpg,.jpeg`) and the server's real
support — the Open WebUI pipe README notes scanned PDFs and images still return a
clear error, so surface that state honestly rather than showing a spinner forever.

**Overview — data mapping. This is where the kit will lie if you let it.**
`GET /metrics/summary` returns only request count, refusal rate, p50/p95 latency,
average retrieved hits, and the answer-mode breakdown. The kit's bento wants more.
For each panel:

| Kit panel | Reality |
|---|---|
| Questions today / People using it / Documents available / Typical answer time / Rated helpful | Only request count and p50 exist. "People using it" needs a per-user identity that does not exist yet — drop until §1's account decision lands. "Rated helpful" needs a feedback mechanism that does not exist — drop or build it as a separate proposal. "Documents available" comes from the documents store. |
| Questions over time (area) | Derivable from timestamps in `logs/query_timings.jsonl`. |
| When people ask (hour × weekday heatmap) | Derivable from the same timestamps. |
| Most-used documents | Derivable — `query_timings.jsonl` records per-query `doc_id`/`section_path`/`score`. |
| Who is asking (department donut) | **Not available** — department is a document attribute, not a query attribute. Either drop it or reframe as documents-by-department from the documents store, and tell me which you chose. |
| Answer quality (lines) | Needs the review set from `eval/`. Wire it if the data is there; otherwise drop. |
| How long answers take (histogram, p95 marker) | Derivable from `elapsed_ms` in the timings log. p95 already exists in the summary. |
| Recent activity feed | Derivable, but must stay metadata-only — never render question text or document content into a feed. |

Extend `app/api/metrics.py` for what is derivable. Anything you cannot back with real
data: leave it out and list it for me. Ship zero demo numbers. Where a panel is real
but empty, show the kit's empty state, not a zero.

Then apply §4's copy rules to every panel you keep: plain-language Vietnamese labels,
a one-line hint each, jargon in tooltips, and correct `betterWhen` direction.

## 9. Phase 4 — chat UI

**Blocked on the §1 security note and the §7 account decision. Do not start until both
are resolved.**

When cleared: adapt `ui_kits/chatbot/ChatScreen.jsx` + `ChatParts.jsx` under
`frontend/src/chat/`, built into the same `app/static/dist/`, wired to the existing
`POST /v1/chat/completions` SSE stream. Keep the kit's component structure intact.

Port all of it: the thread with numbered citations opening the right-hand
`--panel-width` source panel showing passage, document, page, department, and
"% similarity"; the empty state with grouped prompt suggestions; the composer with
attachment chips and parsing state; the no-match state with next-step suggestions;
the sidebar with theme toggle; and the trust line under the composer — the design
system specifies "Your data stays on the internal network" as a recurring brand
promise, so ship it in Vietnamese.

- Prompt suggestions come from `scripts/open_webui/prompt_suggestions.json`, not the
  kit's placeholders. That file is the real Vietnamese copy.
- Citation targets are the existing public read-only routes `/documents/{id}/view`
  and `/documents/{id}/file` allowed by `_PUBLIC_DOC_RE`. Use those; do not widen the
  regex.
- KaTeX must render `$...$` and `$$...$$`, self-hosted — Open WebUI was providing this.
- Port `mobile.html`'s 390px drawer behavior.
- Handle the states the kit does not: stream error, model cold-start (the README notes
  formula-heavy work can take 1–3 minutes on CPU), and request timeout.

**This does not remove Open WebUI.** Port 3000 and `scripts/open_webui/` keep running
untouched so both can run side by side until `/chat` reaches parity. Before you write
chat code, give me a gap list: conversation history and persistence, per-user auth,
the 📥 Nạp tài liệu ingest pipe, file attachment handling, and anything else Open
WebUI does today that `/chat` will not — with what each would cost to build.

## 10. Phase 5 — realign the Open WebUI skin

While Open WebUI is still in service it will sit next to the new UI in the old
palette, which will look broken. Update `scripts/open_webui/apply_branding.py`:
- Move `BV_BLUE`/`BV_BLUE_DARK`/`BV_NAVY`/`BV_GOLD` onto the design system's brand
  values, and regenerate the logo, favicon, and splash from the real lockup.
- Extend the marker-delimited `BRAND_CSS` block toward the new tokens as far as
  Open WebUI's markup allows. This will approximate, never match — that is expected
  and is exactly why Phase 4 exists.
- Keep the script's existing guarantees intact: idempotent, marker-delimited, offline,
  backs up `webui.db` first, refuses to run while Open WebUI is up, and never clobbers
  an admin's edited suggestions without `--force`.

## 11. Phase 6 — documentation

Update in the repo's existing style and show me the diff:
- `CLAUDE.md` deployment paragraph (~line 7): still Docker-free native venvs on the
  target machine, now with a dev-machine-only frontend build whose output is
  committed. State explicitly that the deployment machine never runs npm.
- `CLAUDE.md` **Frontend** line (~line 22): it says Open WebUI today. Describe the real
  state — landing at `/`, admin console, chat at `/chat`, and Open WebUI's remaining role.
- `CLAUDE.md` project-structure tree: add `frontend/`, `app/static/dist/`,
  `app/static/assets/`, `app/static/fonts/`.
- A short note on where the design system lives (`/Users/haphan/Desktop/bv-ai-agent/`,
  external to this repo) and that tokens and components flow from there, so nobody
  hand-edits vendored tokens.
- `README.md` is bilingual and written for the manager who deploys — update the
  screenshots and any step that changed.
- `.env.example` if Phase 4 changed anything about `API_HOST`, `API_SHARED_SECRET`,
  or `ADMIN_PASSWORD`.
- **Leave the five security rules exactly as written.** If anything you built sits
  near one, say so rather than editing the rule.

## 12. Quality bar

- Both themes correct on every screen; contrast holds in dark. Text on navy, gold on
  navy, and every `-subtle` pairing must clear WCAG AA.
- Keyboard: visible `--focus-ring` on every interactive element, logical tab order,
  Escape closes modals and the source panel, focus trapped in modals and restored on
  close. The dropzone needs a keyboard path, not drag-and-drop alone.
- Screen readers: real landmarks, labelled controls, `aria-live` on the streaming
  answer and on upload status.
- `prefers-reduced-motion` respected.
- Nothing loads over the network at runtime — verified per screen with devtools offline.
- A clean checkout with no Node installed still serves every screen from Python alone.
  Verify this explicitly; it is the condition the build step is permitted under.
- Vietnamese renders with no diacritic clipping at every size; check the tightest
  leading you shipped.
- Tabular numerals on every metric. No emoji in chrome. No third-party icon set.
- Every pre-existing admin action still works against its original endpoint — walk
  through them and report the result of each.
- Test at 1440, 1280, 768, and 390.
- Screenshot every screen in both themes and show them next to
  `/Users/haphan/Desktop/bv-ai-agent/screenshots/*-v2.png`.

## 13. How to work

Stop after every phase and show me the result before starting the next. Phases 4 and 7
have explicit approval gates; respect them.

When the kit and reality disagree — a panel with no data behind it, a form implying a
user store that does not exist, an English label that must become Vietnamese — do not
quietly pick one. Build what is real, and tell me what you dropped and why. A list of
honest gaps at the end is worth more to me than a screen that demos well and lies.
