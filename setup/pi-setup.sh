#!/usr/bin/env bash
# Bardo War Room — Raspberry Pi setup
# Kör via SSH eller Raspberry Pi Connect terminal:
#   curl -sSL https://raw.githubusercontent.com/<repo>/main/setup/pi-setup.sh | bash
#   eller: bash setup/pi-setup.sh
set -euo pipefail

WARROOM_DIR="$HOME/war-room"
PORT=8080

echo "=== Bardo War Room — Pi Setup ==="
echo ""

# 1. Beroenden
echo "[1/6] Installerar beroenden..."
sudo apt-get update -qq
sudo apt-get install -y -qq chromium-browser unclutter python3 python3-venv > /dev/null 2>&1
echo "  OK"

# 2. Kopiera filer (om scriptet körs från repot)
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$SCRIPT_DIR/war-room.html" ]; then
  echo "[2/6] Kopierar filer från repo..."
  mkdir -p "$WARROOM_DIR/scripts"
  cp "$SCRIPT_DIR/war-room.html" "$WARROOM_DIR/"
  cp "$SCRIPT_DIR/scripts/hubspot_export_pipeline_data.py" "$WARROOM_DIR/scripts/"
  cp "$SCRIPT_DIR/scripts/hubspot_export_cd_data.py" "$WARROOM_DIR/scripts/"
  cp "$SCRIPT_DIR/run-local.sh" "$WARROOM_DIR/" 2>/dev/null || true
  echo "  OK"
else
  echo "[2/6] Kör från Pi - säkerställ att $WARROOM_DIR finns med alla filer"
  mkdir -p "$WARROOM_DIR/scripts"
fi

# 3. .env
if [ ! -f "$WARROOM_DIR/.env" ]; then
  echo ""
  echo "[3/6] Behöver HUBSPOT_API_TOKEN."
  read -rp "  Klistra in token (pat-eu1-...): " TOKEN
  echo "HUBSPOT_API_TOKEN=$TOKEN" > "$WARROOM_DIR/.env"
  chmod 600 "$WARROOM_DIR/.env"
  echo "  Sparad i $WARROOM_DIR/.env"
else
  echo "[3/6] .env finns redan"
fi

# 4. Första datahämtning
echo "[4/6] Hämtar data från HubSpot..."
cd "$WARROOM_DIR"
python3 scripts/hubspot_export_pipeline_data.py
python3 scripts/hubspot_export_cd_data.py

# 5. Crontab — data-refresh var 5 min + HTTP-server vid boot
echo "[5/6] Sätter upp crontab..."
CRON_REFRESH="*/5 * * * * cd $WARROOM_DIR && python3 scripts/hubspot_export_pipeline_data.py >> /tmp/warroom-sync.log 2>&1 && python3 scripts/hubspot_export_cd_data.py >> /tmp/warroom-sync.log 2>&1"
CRON_SERVER="@reboot cd $WARROOM_DIR && python3 -m http.server $PORT >> /tmp/warroom-server.log 2>&1 &"

(crontab -l 2>/dev/null | grep -v "warroom\|war-room\|hubspot_export"; echo "$CRON_REFRESH"; echo "$CRON_SERVER") | crontab -
echo "  Cron: data var 5 min + HTTP-server vid boot"

# 6. Kiosk-mode autostart
echo "[6/6] Sätter upp kiosk autostart..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/warroom-kiosk.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=War Room Kiosk
Exec=bash -c 'sleep 10 && xset s off && xset -dpms && xset s noblank && unclutter -idle 0 & chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --incognito --check-for-update-interval=31536000 http://localhost:$PORT/war-room.html'
X-GNOME-Autostart-enabled=true
DESKTOP
echo "  Chromium kiosk startar vid inloggning"

echo ""
echo "=== Klart! ==="
echo ""
echo "  Dashboard: http://localhost:$PORT/war-room.html"
echo "  Data uppdateras var 5 min via cron"
echo "  Chromium kiosk startar automatiskt vid boot"
echo ""
echo "  Testa nu:  chromium-browser --kiosk http://localhost:$PORT/war-room.html"
echo "  Loggar:    tail -f /tmp/warroom-sync.log"
echo ""
echo "  Starta om för full autostart, eller kör manuellt:"
echo "    cd $WARROOM_DIR && python3 -m http.server $PORT &"
echo "    chromium-browser --kiosk http://localhost:$PORT/war-room.html"
