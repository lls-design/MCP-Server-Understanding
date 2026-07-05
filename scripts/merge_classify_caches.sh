#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

workers=()
for i in 0 1 2 3; do
  f="tool_analyzer/api_cache_classify_shard${i}.json"
  [[ -f "$f" ]] && workers+=("$f")
done

"$ROOT/.venv/bin/python3" scripts/merge_api_caches.py \
  --main tool_analyzer/api_cache.json \
  --workers "${workers[@]}"

echo "Classify cache merged into tool_analyzer/api_cache.json"
