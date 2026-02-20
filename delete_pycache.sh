#!/usr/bin/env bash
# delete_pycache.sh
# Recursively delete all __pycache__ folders in a project

set -euo pipefail

# Root dir (default = current dir)
ROOT="${1:-.}"

echo "🔍 Searching for __pycache__ folders under: $ROOT"
find "$ROOT" -type d -name "__pycache__" -print -exec rm -rf {} +

echo "✅ Done. All __pycache__ folders removed."
