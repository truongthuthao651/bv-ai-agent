# Day 7 demo script — 4 questions that show the week's work

Companion to `roadmap.md`'s Day 7 wrap-up. Run these against the native stack
(`./scripts/run_native.sh`, then open `http://localhost:8000`) in this order.
Each one exercises a specific, previously-broken behavior fixed Days 1-6.

**Setup note**: this machine's `.env` still ships `API_HOST=127.0.0.1` /
`API_PUBLIC_BASE_URL=http://localhost:8000` (loopback), so citation links
only resolve when browsing from this machine — Day 5's STRETCH item only
added a startup warning + LAN-IP suggestion when someone opens `API_HOST` to
`0.0.0.0` (see `scripts/run_native.sh`), it does not change today's default.
Demo 1 below should be run from this machine, not "citation clickable from
another laptop on the LAN" — that would require deliberately reconfiguring
`.env` first, which is out of scope for a demo.

---

## 1. A 3-product summary that used to flat-refuse (AGENT4, fixed Day 6)

**Ask**: *"Tóm tắt các quyền lợi chính của An Vui Toàn Diện, An Bình Trọn Đời
và An Phú Liên Kết"*

**Before (2026-08-05 audit, Phase 5 adversarial mode e)**: flat refusal —
*"Tôi không tìm thấy thông tin trong tài liệu."* — despite all 3 products
being fully indexed, because `mentioned_doc_titles()` could only resolve one
of the three titles (a `>=2`-distinctive-token floor two of the three titles'
brand words couldn't reach; see `adv_e` in `eval/golden_set.jsonl` for the
full root-cause writeup).

**Now**: a real per-product summary, each product's benefits cited
separately, with resolving `[n]` citations for all three.

**What this shows**: the corpus-relative "dynamic distinctiveness" fix in
`app/retrieval/product_scope.py` — a structural fix, not a one-off keyword
patch, so it self-corrects if a 4th/5th product is ever indexed.

---

## 2. The new "Chất lượng & hiệu năng" metrics view (Day 4)

**Do**: open the admin dashboard, scroll to "Chất lượng & hiệu năng", pick a
time window.

**Before**: no way to see refusal rate, latency percentiles, or answer-mode
breakdown without reading `logs/query_timings.jsonl` by hand.

**Now**: `GET /metrics/summary` aggregates it — refusal rate, p50/p95
latency, grounded/advisory/hybrid/refusal breakdown, retrieved-hit counts —
read-only, local-only, metadata only (never query/answer text).

**What this shows**: for the first time this week, a manager can look at one
screen and ask "is this thing actually being useful/safe this week" without
needing an engineer to grep a log file.

---

## 3. A malformed upload rejected cleanly instead of orphaning a file (SEC4, Day 3)

**Do**: in the admin upload form, upload a file well over `MAX_UPLOAD_MB`
(or a file with a bad extension the parser rejects), then check `/documents`
and the upload directory.

**Before**: `dest.write_bytes(await file.read())` with no size cap — a huge
or malformed upload could partially write a file with no cleanup on failure
(M14 in the original audit).

**Now**: `_write_upload_capped` streams and rejects once the file crosses
`MAX_UPLOAD_MB`, and the endpoint cleans up the partial file on ANY exception
in the pipeline (bad MIME, parser failure, or size cap) — no orphaned file,
no half-ingested document left in Qdrant.

**What this shows**: a routine admin mistake (wrong file, too-big file) now
fails loudly and cleanly instead of leaving silent debris behind.

---

## 4. A coverage question with a stated disqualifying fact (AGENT2 family, Day 5 prompt fix)

**Ask**: *"Tôi tham gia An Bình Trọn Đời, bị tai nạn giao thông khi đang lái
xe với nồng độ cồn vượt mức cho phép và tử vong. Người thụ hưởng có được chi
trả quyền lợi tử vong không?"*

**Before (2026-08-05 audit, AGENT2 finding)**: the exclusion clause (Điều 6)
was retrieved and cited, but the answer never connected it to the question's
own stated fact — a generic "chưa thể kết luận dứt khoát, cần đối chiếu..."
non-answer instead of applying the retrieved exclusion.

**Now**: golden-set item `q43` gates this exact scenario (`must_say` the
exclusion applies) as a permanent regression test — this is one of the 6
historical failure modes promoted from one-off prose in `CLAUDE.md` into a
`--strict`-gated golden-set item this week (roadmap Day 5, task 4).

**What this shows**: the difference between "we noticed this once" and "this
can never silently regress again without failing CI."

---

*Two known, honestly-documented gaps NOT to demo as fixed (they aren't):*
`q35`/`q52` (surrender-value completeness — the model sometimes omits the
24-month qualifying condition depending on phrasing) and `q59` (reaches the
right conclusion but not always in the exact standalone-refusal sentence
format). See `roadmap.md`'s Day 5/6 actual-result sections for the full
writeups.
