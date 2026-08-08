# Phase 7 implementation changelog

Tracks what changed, why, and what was deliberately skipped, per `AUDIT_PROMPT.md` Phase 7.
One entry per commit. Findings IDs reference `audit/REPORT.md` §6.3.

---

## Wave 0 — Ship blockers

### `fbaafec` — Redesign: bespoke React frontend, RBAC accounts, retire Open WebUI
Not a Phase 7 fix — this finally commits the entire redesign + RBAC + Open-WebUI-removal
changeset that had been sitting uncommitted in the working tree since earlier in this session
(the audit itself evaluated this exact state, see `audit/00-system-map.md` §0.4). Landing it was
a prerequisite for every subsequent Wave 0+ commit. 440 tests pass, ruff clean, frontend rebuilt
and verified before committing.

**Side effect: resolves OPS-A.** `app/static/dist/` is now tracked in git — a fresh clone once
again serves the frontend. No separate commit needed for this finding.

### `ad26e20` — security: require a session for /documents/{id}/view and /file (SEC-A)
**Fixed.** These two citation-link routes had no session check at all — matched into
`auth.PUBLIC_PREFIXES` via a regex, they were reachable by anyone, not just employees. Since
`doc_id` is a deterministic `uuid5` of the uploaded filename, anyone who could guess a real
filename could read full document content with zero credentials, on the default LAN-open config.
Removed the public-path carve-out so both routes now require any signed-in account (not
admin-only — employees still need to open citations from `/chat`). Added regression tests:
sessionless → 401/redirect; employee session → reaches the real handler (404 for a nonexistent
doc, not a 401/403 from the auth layer). 442 tests pass (2 new), ruff clean, npm lint clean.

**Skipped for now**: the zip/XML-bomb resilience question flagged alongside this in
`audit/01-engineering.md` §1.4 remains an unverified suspicion, not a confirmed gap — no fix
attempted without first confirming there's something to fix.

### `5558dbf` — security: default API_HOST to loopback, not LAN-exposed (SEC-B)
**Fixed.** `settings.py`'s code-level fallback default was `api_host="0.0.0.0"` (LAN-exposed),
contradicting its own neighboring comment which already claimed loopback was the default.
Combined with `api_shared_secret` defaulting to empty, a fresh install with no `.env` (or one
missing this line) came up LAN-reachable with no auth on `/v1/chat/completions` by default.
Flipped to `"127.0.0.1"`, matching `.env.example`'s already-correct documented value — this is a
fail-safe-default fix, not a behavior change for any real deployment (which already sets
`API_HOST` explicitly). 442 tests pass, ruff clean.

Wave 0 complete: **SEC-A** and **SEC-B** fixed; **OPS-A** resolved as a side effect of the
foundational redesign commit.


