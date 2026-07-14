# Nạp tài liệu từ Open WebUI (port 3000)

`ingest_pipe.py` is an Open WebUI **Pipe function** that adds a "📥 Nạp tài
liệu" entry to the model dropdown in Open WebUI. Users select it, attach a
file, and send — the file is forwarded to our own `POST /ingest` (equation-safe
chunking, formula verbalization, bge-m3 hybrid indexing) and the result comes
back as the chat reply. This runs entirely inside the port-3000 web app; no
separate admin page is needed for day-to-day uploads.

Why a Pipe function, and not Open WebUI's native "+/paperclip" upload:
Open WebUI's built-in attachment flow always goes through its own internal
RAG (its own chunking/embedding/vector store) with no supported way to
redirect it to an external ingestion API
([open-webui/open-webui#17293](https://github.com/open-webui/open-webui/issues/17293),
open upstream). A Pipe function is the standard workaround: it registers as
its own selectable "model" whose code we control.

## One-time setup (admin, ~2 minutes)

1. **Create an Open WebUI API key** (needed so the Pipe can read back the
   bytes of a file you attach): open http://localhost:3000 → bottom-left
   profile menu → **Settings** → **Account** → **API Keys** → **Create new
   secret key**. Copy it.
2. **Install the function**: **Admin Panel** (profile menu) → **Settings** →
   **Functions** → **+** → paste the entire contents of `ingest_pipe.py` →
   **Save**. Open WebUI should detect it as a `pipe`-type function named
   "Nạp tài liệu" — enable it (toggle on).
3. **Configure its Valves**: click the ⚙️ gear on the function → paste the API
   key from step 1 into `OPENWEBUI_API_KEY`. The other defaults fit the native
   (no-Docker) deployment: `INGEST_API_BASE_URL=http://localhost:8000`,
   `OPENWEBUI_INTERNAL_URL=http://localhost:3000`. On the Docker dev stack set
   them to the in-container addresses instead: `http://api:8000` and
   `http://localhost:8080`.

## Using it (everyone)

1. In a chat, open the model dropdown at the top and select **📥 Nạp tài liệu**.
2. Attach a file (paperclip icon) — currently supported: `.md`, `.docx`,
   `.xlsx`, `.pdf` (with a text layer), `.yaml`/`.yml` (scanned PDFs/images
   are still in development and will return a clear error if selected).
3. Send. The reply reports the document title, chunk count, and doc id, or a
   specific error if something went wrong.
4. Switch back to the normal chat model to ask questions — retrieval/citation
   already happens server-side in our `/v1/chat/completions`, so newly
   ingested documents are searchable immediately.

## Known limitations

- **Slow on CPU.** Formula-heavy documents call the local LLM once per
  math-containing chunk during enrichment; a small glossary/policy file can
  take 1-3 minutes. `REQUEST_TIMEOUT` (default 280s) covers this.
- **Wasted duplicate embedding.** Attaching a file to *any* chat message also
  makes Open WebUI extract+embed a copy into its own local vector store, as a
  side effect of the attach action itself — this happens before our Pipe even
  runs and isn't something a Pipe function can suppress (that copy is never
  read by anything; our chat endpoint only queries our own Qdrant collection).
- **Attachment schema is best-effort.** Open WebUI's internal file-attachment
  shape isn't a stable public contract and has changed across versions. If a
  file fails with "Không xác định được tệp đính kèm", copy the error (it
  includes the raw data Open WebUI sent) so the extraction logic in
  `ingest_pipe.py` can be adjusted.
- Only one document type is auto-detected from the file extension (matching
  `POST /ingest`'s default behavior) — there is currently no way to override
  `doc_type` from the Open WebUI chat UI.
