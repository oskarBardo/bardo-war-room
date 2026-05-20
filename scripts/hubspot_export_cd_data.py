#!/usr/bin/env python3
"""
Export CD Delivery pipeline data from HubSpot to war-room-cd-data.js.
The war-room.html loads this file to populate the kanban + backlog.

Usage:
  python3 scripts/hubspot_export_cd_data.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = "https://api.hubapi.com"
CD_PIPELINE = "3760960735"
OBJECT = "0-970"

STAGE_LABELS: dict[str, str] = {
    "5254828223": "incoming",
    "5254828224": "transfer",
    "5254828225": "health",
    "5254828226": "calc",
    "5254828227": "presentation",
    "5254828228": "postfix",
    "5261997261": "waiting",
    "5254828239": "closed",
}

OWNER_MAP: dict[str, str] = {
    "67401979": "Oskar",
    "67402028": "CJ",
    "32352101": "Jenny",
    "67402036": "Ingemar",
    "32255473": "Owais",
    "31790661": "Kristin",
}

PROJECT_PROPS = [
    "hs_name",
    "hs_pipeline_stage",
    "hs_start_date",
    "hs_target_due_date",
    "hs_status",
    "hs_priority",
    "hs_lastmodifieddate",
    "hs_v2_date_entered_current_stage",
    "hubspot_owner_id",
    "project_type",
    "linked_deal_id",
    "cd_acv",
    "cd_volume",
    "cd_type",
    "cd_complexity",
    "cd_blocker",
    "cd_scope",
    "cd_presentation_date",
]


def req(method: str, path: str, body: Any = None, token: str = "") -> Any:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
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


def fetch_cd_projects(token: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        body: dict[str, Any] = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "hs_pipeline",
                            "operator": "EQ",
                            "value": CD_PIPELINE,
                        }
                    ]
                }
            ],
            "properties": PROJECT_PROPS,
            "limit": 100,
        }
        if after:
            body["after"] = after
        data = req("POST", f"/crm/v3/objects/{OBJECT}/search", body, token)
        out.extend(data.get("results", []))
        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return out


def fmt_acv(val: str | None) -> str:
    if not val:
        return ""
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return val
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def company_name(hs_name: str) -> str:
    if " — " in hs_name:
        return hs_name.split(" — ")[0].strip()
    if " - " in hs_name:
        return hs_name.split(" - ")[0].strip()
    return hs_name


def main() -> None:
    token = load_env()
    projects = fetch_cd_projects(token)
    now = datetime.now(timezone.utc)

    records: list[dict[str, Any]] = []
    for p in projects:
        props = p.get("properties") or {}
        stage_id = props.get("hs_pipeline_stage") or ""
        stage = STAGE_LABELS.get(stage_id, stage_id)

        owner_id = props.get("hubspot_owner_id") or ""
        try:
            owner_id = str(int(float(owner_id)))
        except (TypeError, ValueError):
            pass
        owner = OWNER_MAP.get(owner_id, owner_id)

        modified = props.get("hs_lastmodifieddate") or props.get("hs_start_date") or ""
        days_in_stage = 0
        entry = props.get("hs_v2_date_entered_current_stage")
        if entry:
            try:
                e = entry.replace("Z", "+00:00")
                dt = datetime.fromisoformat(e)
                days_in_stage = max(0, (now - dt).days)
            except (TypeError, ValueError):
                pass

        records.append(
            {
                "id": p["id"],
                "name": company_name(props.get("hs_name") or ""),
                "stage": stage,
                "blocker": (props.get("cd_blocker") or "none").lower(),
                "owner": owner,
                "priority": (props.get("hs_priority") or "medium").lower(),
                "status": (props.get("hs_status") or "").lower().replace("-", "_"),
                "acv": fmt_acv(props.get("cd_acv")),
                "volume": props.get("cd_volume") or "",
                "cd_type": (props.get("cd_type") or "").upper(),
                "complexity": (props.get("cd_complexity") or "").lower(),
                "start": (props.get("hs_start_date") or "")[:10],
                "due": (props.get("hs_target_due_date") or "")[:10],
                "modified": modified[:10] if modified else "",
                "days_in_stage": days_in_stage,
                "presentation_date": (props.get("cd_presentation_date") or "")[:10],
            }
        )

    records.sort(
        key=lambda r: (
            {"high": 0, "medium": 1, "low": 2}.get(r["priority"], 1),
            r["name"].lower(),
        )
    )

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "war-room-cd-data.js")
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    js = f"// Auto-generated by scripts/hubspot_export_cd_data.py at {ts}\n"
    js += f"// {len(records)} CD projects from pipeline {CD_PIPELINE}\n"
    js += f"window.__cdData = {json.dumps(records, indent=2, ensure_ascii=False)};\n"
    js += f'window.__cdDataTimestamp = "{ts}";\n'

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js)

    print(f"Exporterade {len(records)} CD-projekt till {out_path}")
    stage_counts: dict[str, int] = {}
    for r in records:
        stage_counts[r["stage"]] = stage_counts.get(r["stage"], 0) + 1
    for s, c in sorted(stage_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()
