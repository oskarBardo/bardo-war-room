# Bardo War Room

Real-time dashboard for HubSpot pipeline visibility. Designed to run autonomously on a Raspberry Pi.

## Quick start (local)

```bash
cp .env.example .env
# Add your HubSpot Private App token to .env

./run-local.sh
```

## Raspberry Pi setup

```bash
# On the Pi:
git clone git@github.com:bardogroup/bardo-war-room.git ~/war-room
cd ~/war-room
bash setup/pi-setup.sh
```

The setup script installs dependencies, configures cron for 5-minute data refresh, and starts Chromium in kiosk mode on boot.

## Architecture

No backend, no database. Just Python scripts that export HubSpot data to static JS files, served by `python3 -m http.server`.

```
HubSpot API  -->  Python export scripts  -->  .js data files  -->  war-room.html
                  (cron every 5 min)          (static)             (browser)
```

## Files

| File | Purpose |
|------|---------|
| `war-room.html` | Dashboard (single-file HTML/CSS/JS) |
| `scripts/hubspot_export_cd_data.py` | Exports CD Delivery pipeline data |
| `scripts/hubspot_export_pipeline_data.py` | Exports Sales + Lead pipeline data |
| `run-local.sh` | Local dev: export data, start server, open browser |
| `setup/pi-setup.sh` | Raspberry Pi one-time setup |
