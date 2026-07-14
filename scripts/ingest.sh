#!/usr/bin/env bash
# =============================================================================
# Batch-ingest a folder: POST each supported file to the running API's /ingest.
#   bash scripts/ingest.sh data/synthetic
#   bash scripts/ingest.sh data/glossary
# Requires the stack to be up (scripts/run_native.sh, or docker compose up -d
# in docker dev mode). Enrichment calls the local
# LLM once per math chunk, so formula-heavy files can take minutes each.
# =============================================================================
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Read one variable from .env. Never `source` it: values contain spaces and
# UTF-8 (ASSISTANT_NAME, WEBUI_NAME), which the shell would try to execute.
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

API_PORT="$(env_get API_PORT)"
API_PORT="${API_PORT:-8000}"
API_URL="http://localhost:${API_PORT}"
TARGET="${1:-data/synthetic}"

if [[ ! -d "$TARGET" ]]; then
  echo "ERROR: '$TARGET' is not a directory." >&2
  exit 1
fi

# Keep in sync with app/ingestion/router.py (scanned images land with OCR).
SUPPORTED="md markdown docx xlsx pdf yaml yml"

ok=0 failed=0 skipped=0
while IFS= read -r file; do
  ext="$(echo "${file##*.}" | tr '[:upper:]' '[:lower:]')"
  case " $SUPPORTED " in
    *" $ext "*) ;;
    *)
      echo "  [SKIP] $file (unsupported: .$ext)"
      skipped=$((skipped + 1))
      continue
      ;;
  esac

  body="$(mktemp)"
  # Long --max-time: formula verbalization is slow on CPU (see the skill).
  status="$(curl -sS -o "$body" -w '%{http_code}' --max-time 600 \
    -F "file=@${file}" "${API_URL}/ingest" || echo 000)"
  if [[ "$status" == "200" ]]; then
    echo "  [ OK ] $file -> $(cat "$body")"
    ok=$((ok + 1))
  else
    echo "  [FAIL] $file (HTTP $status): $(cat "$body")" >&2
    failed=$((failed + 1))
  fi
  rm -f "$body"
done < <(find "$TARGET" -type f ! -name ".*" | sort)

echo "==> Ingest finished: $ok ok, $failed failed, $skipped skipped."
[[ "$failed" -eq 0 ]] || exit 1
