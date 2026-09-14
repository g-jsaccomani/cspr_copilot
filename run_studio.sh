#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8095}"
echo "🚀 Starting CSPR Copilot & Agentic Studio (Gemini 3.x) on http://localhost:${PORT}"
echo "🔗 Linked Upstream CSPR Repo: /Users/jsaccomani/Documents/Jetsky/Google/CSPR"

if [ -x "/Users/jsaccomani/Documents/Jetsky/My Projects/agentic_grc_copilot/.venv/bin/python" ]; then
  PYTHONPATH="$SCRIPT_DIR" "/Users/jsaccomani/Documents/Jetsky/My Projects/agentic_grc_copilot/.venv/bin/python" -m uvicorn agentic_studio.api.server:app --host 0.0.0.0 --port "$PORT"
else
  PYTHONPATH="$SCRIPT_DIR" python3 -m uvicorn agentic_studio.api.server:app --host 0.0.0.0 --port "$PORT"
fi
