#!/usr/bin/env bash
# =============================================================================
# Batch-ingest a folder of documents (STUB — Phase 1 placeholder).
#   bash scripts/ingest.sh data/synthetic
#   bash scripts/ingest.sh data/glossary
# =============================================================================
set -euo pipefail

TARGET="${1:-data/synthetic}"
echo "TODO(phase-ingestion): POST each file under '$TARGET' to /ingest." >&2
exit 1
