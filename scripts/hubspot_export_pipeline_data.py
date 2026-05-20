#!/usr/bin/env python3
"""
Export Deal + Lead pipeline data from HubSpot to war-room-pipeline-data.js.
The war-room.html loads this file to render the Gapminder bubble chart.

Usage:
  python3 scripts/hubspot_export_pipeline_data.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = "https://api.hubapi.com"

DEAL_PIPELINE = "default"
LEAD_PIPELINE = "2217488629"

DEAL_STAGE_ORDER: dict[str, tuple[int, str]] = {
    "qualifiedtobuy":       (0, "Qualified"),
    "presentationscheduled":(1, "CD Proposal"),
    "5060810972":           (2, "CD Committed"),
    "decisionmakerboughtin":(3, "CD Signed"),
    "contractsent":         (4, "CD Delivered"),
    "3007671501":           (5, "Negotiation"),
    "3243524318":           (6, "Agreement"),
    "3810017490":           (7, "CD opt-out"),
    "closedwon":            (8, "Closed Won"),
    "closedlost":           (9, "Closed Lost"),
}

LEAD_STAGE_ORDER: dict[str, tuple[int, str]] = {
    "3025440982": (0, "Backlogg"),
    "3025440983": (1, "Reached out"),
    "3025440984": (2, "First Meeting"),
    "3172814055": (3, "Hot"),
    "3025440986": (4, "Client sync"),
    "3025440985": (5, "On hold"),
    "4593625313": (6, "Cold"),
    "3026455743": (7, "Not now"),
    "5019106552": (8, "Ghost"),
    "3025440987": (9, "Converted"),
}

OWNER_MAP: dict[str, str] = {
    "67401979":  "Oskar",
    "67402028":  "CJ",
    "32352101":  "Jenny",
    "67402036":  "Ingemar",
    "32255473":  "Owais",
    "31790661":  "Kristin",
}

DEAL_PROPS = [
    "dealname", "dealstage", "pipeline", "amount", "closedate",
    "hubspot_owner_id", "notes_last_updated", "hs_lastmodifieddate",
    "createdate", "icp_segment", "cd_type",
]

LEAD_PROPS = [
    "dealname", "dealstage", "pipeline", "amount", "closedate",
    "hubspot_owner_id", "notes_last_updated", "hs_lastmodifieddate",
    "createdate", "icp_segment",
]


def req(method: str, path: str, body: Any = None, token: str = "") -> Any:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def load_env() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
    token = os.environ.get("HUBSPOT_API_TOKEN", "").strip()
    if not token.startswith("pat-"):
        print("HUBSPOT_API_TOKEN saknas i .env", file=sys.stderr)
        sys.exit(1)
    return token


def search_deals(token: str, pipeline: str, props: list[str]) -> list[dict]:
    out: list[dict] = []
    after: str | None = None
    while True:
        body: dict[str, Any] = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": pipeline}
            ]}],
            "properties": props,
            "limit": 100,
        }
        if after:
            body["after"] = after
        data = req("POST", "/crm/v3/objects/deals/search", body, token)
        out.extend(data.get("results", []))
        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return out


def fmt_amount(val: str | None) -> float:
    if not val:
        return 0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0


def days_since(iso_str: str | None, now: datetime) -> int:
    if not iso_str:
        return 999
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return max(0, (now - dt).days)
    except (TypeError, ValueError):
        return 999


def process_deals(
    raw: list[dict],
    stage_map: dict[str, tuple[int, str]],
    now: datetime,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for d in raw:
        props = d.get("properties") or {}
        stage_id = props.get("dealstage") or ""
        stage_info = stage_map.get(stage_id)
        if not stage_info:
            continue

        owner_id = props.get("hubspot_owner_id") or ""
        try:
            owner_id = str(int(float(owner_id)))
        except (TypeError, ValueError):
            pass

        last_activity = props.get("notes_last_updated") or props.get("hs_lastmodifieddate") or ""
        amount = fmt_amount(props.get("amount"))

        records.append({
            "id": d["id"],
            "name": props.get("dealname") or "",
            "stageIdx": stage_info[0],
            "stageLabel": stage_info[1],
            "stageId": stage_id,
            "amount": amount,
            "owner": OWNER_MAP.get(owner_id, owner_id),
            "closedate": (props.get("closedate") or "")[:10],
            "daysSinceActivity": days_since(last_activity, now),
            "created": (props.get("createdate") or "")[:10],
            "icp": props.get("icp_segment") or "",
        })
    return records


def fetch_all_stage_history(token: str) -> list[dict[str, Any]]:
    """Fetch all deals with propertiesWithHistory=dealstage. Returns raw results."""
    results: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        url = (
            "/crm/v3/objects/deals"
            "?limit=50"
            "&properties=dealname,hubspot_owner_id,pipeline"
            "&propertiesWithHistory=dealstage"
        )
        if after:
            url += f"&after={after}"
        data = req("GET", url, token=token)
        results.extend(data.get("results", []))
        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return results


def extract_events(
    raw_results: list[dict[str, Any]],
    pipeline: str,
    stage_map: dict[str, tuple[int, str]],
) -> list[dict[str, Any]]:
    """Extract stage-change events for a specific pipeline."""
    events: list[dict[str, Any]] = []
    for result in raw_results:
        props = result.get("properties") or {}
        if props.get("pipeline") != pipeline:
            continue
        deal_name = props.get("dealname") or "?"
        history = (result.get("propertiesWithHistory") or {}).get("dealstage") or []
        for entry in history:
            stage_id = entry.get("value") or ""
            ts_str = entry.get("timestamp") or ""
            user_id = str(entry.get("updatedByUserId") or "")
            stage_info = stage_map.get(stage_id)
            if not stage_info or not ts_str:
                continue
            events.append({
                "timestamp": ts_str,
                "actor": OWNER_MAP.get(user_id, user_id),
                "verb": "move",
                "deal": deal_name,
                "dealId": result["id"],
                "toStage": stage_info[1],
            })
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events


_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\u200d]+",
)


def _clean_name(name: str) -> str:
    return _EMOJI_RE.sub("", name).strip()


def build_activity_feed(events: list[dict[str, Any]], max_items: int = 15) -> list[dict[str, Any]]:
    """Format raw events into display-ready feed items."""
    feed: list[dict[str, Any]] = []
    for ev in events[:max_items]:
        try:
            dt = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M")
            date_str = f"{dt.day} {dt.strftime('%b').lower()}"
        except (TypeError, ValueError):
            time_str = "?"
            date_str = ""
        name = _clean_name(ev["deal"])
        if len(name) > 18:
            name = name[:17] + "\u2026"
        actor = ev["actor"]
        if not actor or actor == "None" or actor.isdigit():
            actor = "System"
        feed.append({
            "time": time_str,
            "date": date_str,
            "actor": actor,
            "verb": ev["verb"],
            "deal": name,
            "detail": ev["toStage"],
        })
    return feed


def main() -> None:
    token = load_env()
    now = datetime.now(timezone.utc)

    print("Hämtar Deal Pipeline...")
    raw_deals = search_deals(token, DEAL_PIPELINE, DEAL_PROPS)
    deals = process_deals(raw_deals, DEAL_STAGE_ORDER, now)

    print("Hämtar Lead Pipeline...")
    raw_leads = search_deals(token, LEAD_PIPELINE, LEAD_PROPS)
    leads = process_deals(raw_leads, LEAD_STAGE_ORDER, now)

    active_deals = [d for d in deals if d["stageLabel"] not in ("Closed Won", "Closed Lost")]
    closed_deals = [d for d in deals if d["stageLabel"] in ("Closed Won", "Closed Lost")]

    active_leads = [d for d in leads if d["stageLabel"] not in ("Not now", "Ghost", "Converted")]
    closed_leads = [d for d in leads if d["stageLabel"] in ("Not now", "Ghost", "Converted")]

    print("Hämtar stage history...")
    all_raw = fetch_all_stage_history(token)
    deal_events = extract_events(all_raw, DEAL_PIPELINE, DEAL_STAGE_ORDER)
    lead_events = extract_events(all_raw, LEAD_PIPELINE, LEAD_STAGE_ORDER)

    deal_feed = build_activity_feed(deal_events)
    lead_feed = build_activity_feed(lead_events)

    payload = {
        "deals": {
            "active": sorted(active_deals, key=lambda d: (d["stageIdx"], d["name"])),
            "closed": sorted(closed_deals, key=lambda d: d["name"]),
            "stages": [s[1] for _, s in sorted(DEAL_STAGE_ORDER.items(), key=lambda kv: kv[1][0])
                       if s[1] not in ("Closed Won", "Closed Lost")],
            "activity": deal_feed,
        },
        "leads": {
            "active": sorted(active_leads, key=lambda d: (d["stageIdx"], d["name"])),
            "closed": sorted(closed_leads, key=lambda d: d["name"]),
            "stages": [s[1] for _, s in sorted(LEAD_STAGE_ORDER.items(), key=lambda kv: kv[1][0])
                       if s[1] not in ("Not now", "Ghost", "Converted")],
            "activity": lead_feed,
        },
    }

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "war-room-pipeline-data.js")
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    js = f"// Auto-generated by scripts/hubspot_export_pipeline_data.py at {ts}\n"
    js += f"window.__pipelineData = {json.dumps(payload, indent=2, ensure_ascii=False)};\n"
    js += f'window.__pipelineTimestamp = "{ts}";\n'

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js)

    total_val = sum(d["amount"] for d in active_deals)
    cold = sum(1 for d in active_deals if d["daysSinceActivity"] > 14)
    print(f"\nExporterade {len(active_deals)} aktiva deals ({total_val/1e6:.1f}M SEK, {cold} kalla)")
    print(f"Exporterade {len(active_leads)} aktiva leads")
    print(f"Activity feed: {len(deal_feed)} deal events, {len(lead_feed)} lead events")
    print(f"→ {out_path}")


if __name__ == "__main__":
    main()
