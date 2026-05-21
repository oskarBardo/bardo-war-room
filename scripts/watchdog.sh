#!/usr/bin/env bash
# Watchdog: keeps HTTP server and Chromium alive.
# Run via cron every minute.
set -euo pipefail

WARROOM_DIR="$HOME/war-room"
PORT=8080
URL="http://localhost:$PORT/war-room.html"
LOG="/tmp/warroom-watchdog.log"

ts() { date "+%Y-%m-%d %H:%M:%S"; }

# 1. HTTP server
if ! curl -sf -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then
    echo "$(ts) HTTP server down — restarting" >> "$LOG"
    cd "$WARROOM_DIR"
    python3 -m http.server "$PORT" >> /tmp/warroom-server.log 2>&1 &
    sleep 2
fi

# 2. Chromium (only if DISPLAY/WAYLAND is available)
if [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ]; then
    if ! pgrep -f "chromium.*kiosk" > /dev/null 2>&1; then
        echo "$(ts) Chromium down — restarting" >> "$LOG"
        CHROME=$(command -v chromium-browser 2>/dev/null || command -v chromium 2>/dev/null)
        if [ -n "$CHROME" ]; then
            $CHROME --kiosk --noerrdialogs --disable-infobars \
                --disable-session-crashed-bubble --incognito \
                "$URL" >> /tmp/warroom-chromium.log 2>&1 &
        fi
    fi
fi
