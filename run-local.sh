#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8080}"

if [ ! -f "$ROOT/.env" ]; then
  echo "Saknar .env med HUBSPOT_API_TOKEN. Se .env.example"
  exit 1
fi

echo "=== Exporterar HubSpot-data ==="
python3 "$ROOT/scripts/hubspot_export_pipeline_data.py"
python3 "$ROOT/scripts/hubspot_export_cd_data.py"

echo ""
echo "=== Startar HTTP-server på localhost:$PORT ==="
echo "    Dashboard: http://localhost:$PORT/war-room.html"
echo "    Auto-reload var 5 min (JS polling)"
echo "    Ctrl+C för att stoppa"
echo ""

if command -v open &>/dev/null; then
  open "http://localhost:$PORT/war-room.html" &
elif command -v xdg-open &>/dev/null; then
  xdg-open "http://localhost:$PORT/war-room.html" &
fi

cd "$ROOT"
python3 -m http.server "$PORT"
