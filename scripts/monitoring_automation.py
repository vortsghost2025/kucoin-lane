#!/usr/bin/env python3
"""
KuCoin lane monitoring automation.

- Hourly: capture a monitoring snapshot and append structured JSONL history.
- Daily/Weekly/Monthly: analyze snapshot history and emit markdown reports.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / "lanes" / "kucoin" / "state" / "monitoring"
DOCS_DIR = REPO_ROOT / "docs" / "automation"
HISTORY_JSONL = STATE_DIR / "hourly_snapshots.jsonl"
SESSION_STATE_PATH = REPO_ROOT / "lanes" / "kucoin" / "inbox" / "SESSION_STATE.json"
HEARTBEAT_CANDIDATES = [
    REPO_ROOT / "bot_heartbeat_dry_run.json",
    REPO_ROOT / "bot_heartbeat_live.json",
    REPO_ROOT / "bot_heartbeat.json",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_cmd(args: List[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def parse_systemd_units() -> Dict[str, Any]:
    output = run_cmd(["systemctl", "list-units", "--type=service", "--all"])
    kucoin_units: List[str] = []
    governance_units = 0

    if output:
        for line in output.splitlines():
            compact = " ".join(line.split())
            if "@kucoin.service" in compact and compact.startswith("we4free-"):
                kucoin_units.append(compact)
            if compact.startswith("we4free-") and any(
                f"@{lane}.service" in compact
                for lane in ("archivist", "kernel", "library", "swarmmind")
            ):
                governance_units += 1

    return {
        "kucoin_units": kucoin_units,
        "governance_unit_count": governance_units,
    }


def select_heartbeat_file() -> Optional[Path]:
    existing = [path for path in HEARTBEAT_CANDIDATES if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def collect_snapshot() -> Dict[str, Any]:
    ts = utc_now()
    git_head = run_cmd(["git", "rev-parse", "--short", "HEAD"])
    git_branch = run_cmd(["git", "branch", "--show-current"])
    session_state = read_json(SESSION_STATE_PATH)

    heartbeat_file = select_heartbeat_file()
    heartbeat = read_json(heartbeat_file) if heartbeat_file else None

    systemd_data = parse_systemd_units()
    snapshot = {
        "timestamp_utc": iso_utc(ts),
        "repo_path": str(REPO_ROOT),
        "git_head": git_head,
        "git_branch": git_branch,
        "session_state_path": str(SESSION_STATE_PATH.relative_to(REPO_ROOT)),
        "session_state_exists": session_state is not None,
        "session_state": session_state,
        "heartbeat_path": str(heartbeat_file.relative_to(REPO_ROOT)) if heartbeat_file else None,
        "heartbeat_exists": heartbeat is not None,
        "heartbeat": heartbeat,
        "systemd": systemd_data,
    }
    return snapshot


def append_history(snapshot: Dict[str, Any]) -> None:
    with HISTORY_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, separators=(",", ":")) + "\n")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def render_snapshot_markdown(snapshot: Dict[str, Any]) -> str:
    now = snapshot["timestamp_utc"]
    session = snapshot.get("session_state") or {}
    heartbeat = snapshot.get("heartbeat") or {}
    units = snapshot["systemd"]
    kucoin_unit_count = len(units.get("kucoin_units", []))

    return f"""OUTPUT_PROVENANCE:
  agent: monitoring-automation
  lane: kucoin
  generated_at: {now}
  source: scripts/monitoring_automation.py
  type: hourly-snapshot

# KuCoin Monitoring Snapshot ({now})

## Repo
- Path: `{snapshot["repo_path"]}`
- Head: `{snapshot.get("git_head") or "unknown"}`
- Branch: `{snapshot.get("git_branch") or "unknown"}`

## SESSION_STATE
- Path: `{snapshot["session_state_path"]}`
- Exists: `{snapshot["session_state_exists"]}`
- Status: `{session.get("status")}`
- Phase: `{session.get("phase")}`
- Final: `{session.get("final")}`
- Cycle: `{session.get("cycle")}`
- Mode: `{session.get("mode")}`

## Heartbeat
- Path: `{snapshot.get("heartbeat_path")}`
- Exists: `{snapshot.get("heartbeat_exists")}`
- Status: `{heartbeat.get("status")}`
- Step: `{heartbeat.get("step")}`
- Cycle: `{heartbeat.get("cycle")}`
- Mode: `{heartbeat.get("mode")}`

## systemd
- KuCoin lane unit count: `{kucoin_unit_count}`
- Governance lane unit count (archivist/kernel/library/swarmmind): `{units.get("governance_unit_count", 0)}`
"""


def write_snapshot_artifacts(snapshot: Dict[str, Any]) -> Path:
    ts_file = snapshot["timestamp_utc"].replace(":", "-")
    snapshot_path = DOCS_DIR / f"MONITORING_SNAPSHOT_{ts_file}.md"
    write_text(snapshot_path, render_snapshot_markdown(snapshot))
    write_text(DOCS_DIR / "latest-monitoring-snapshot.md", render_snapshot_markdown(snapshot))
    return snapshot_path


def parse_history() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not HISTORY_JSONL.exists():
        return rows
    for line in HISTORY_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


@dataclass
class AnalysisWindow:
    period: str
    start: datetime
    end: datetime


def select_window(period: str) -> AnalysisWindow:
    end = utc_now()
    if period == "daily":
        start = end - timedelta(days=1)
    elif period == "weekly":
        start = end - timedelta(days=7)
    elif period == "monthly":
        start = end - timedelta(days=30)
    else:
        raise ValueError(f"Unsupported period: {period}")
    return AnalysisWindow(period=period, start=start, end=end)


def parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def in_window(rows: Iterable[Dict[str, Any]], window: AnalysisWindow) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for row in rows:
        ts = parse_ts(str(row.get("timestamp_utc", "")))
        if ts is None:
            continue
        if window.start <= ts <= window.end:
            selected.append(row)
    return selected


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "samples": 0,
            "session_exists_pct": 0.0,
            "heartbeat_exists_pct": 0.0,
            "status_counts": {},
            "phase_counts": {},
            "final_true_pct": 0.0,
            "kucoin_unit_seen_pct": 0.0,
            "governance_unit_avg": 0.0,
            "interval_minutes_median": None,
            "interval_minutes_max": None,
        }

    samples = len(rows)
    session_exists = sum(1 for r in rows if r.get("session_state_exists"))
    heartbeat_exists = sum(1 for r in rows if r.get("heartbeat_exists"))

    statuses = Counter(
        str((r.get("session_state") or {}).get("status"))
        for r in rows
        if (r.get("session_state") or {}).get("status") is not None
    )
    phases = Counter(
        str((r.get("session_state") or {}).get("phase"))
        for r in rows
        if (r.get("session_state") or {}).get("phase") is not None
    )

    final_true = sum(
        1
        for r in rows
        if (r.get("session_state") or {}).get("final") is True
    )

    kucoin_units_seen = sum(
        1 for r in rows if len((r.get("systemd") or {}).get("kucoin_units", [])) > 0
    )
    governance_counts = [
        int((r.get("systemd") or {}).get("governance_unit_count", 0))
        for r in rows
    ]

    timestamps = sorted(
        ts for ts in (parse_ts(str(r.get("timestamp_utc", ""))) for r in rows) if ts is not None
    )
    deltas = [
        (timestamps[i] - timestamps[i - 1]).total_seconds() / 60.0
        for i in range(1, len(timestamps))
    ]

    return {
        "samples": samples,
        "session_exists_pct": (session_exists / samples) * 100.0,
        "heartbeat_exists_pct": (heartbeat_exists / samples) * 100.0,
        "status_counts": dict(statuses),
        "phase_counts": dict(phases),
        "final_true_pct": (final_true / samples) * 100.0,
        "kucoin_unit_seen_pct": (kucoin_units_seen / samples) * 100.0,
        "governance_unit_avg": statistics.mean(governance_counts) if governance_counts else 0.0,
        "interval_minutes_median": statistics.median(deltas) if deltas else None,
        "interval_minutes_max": max(deltas) if deltas else None,
    }


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def render_analysis_markdown(window: AnalysisWindow, summary: Dict[str, Any], row_count: int) -> str:
    now = iso_utc(utc_now())
    statuses = ", ".join(f"{k}:{v}" for k, v in summary["status_counts"].items()) or "none"
    phases = ", ".join(f"{k}:{v}" for k, v in summary["phase_counts"].items()) or "none"
    interval_med = summary["interval_minutes_median"]
    interval_max = summary["interval_minutes_max"]
    interval_text = (
        f"median={interval_med:.1f}m, max={interval_max:.1f}m"
        if interval_med is not None and interval_max is not None
        else "insufficient data"
    )

    return f"""OUTPUT_PROVENANCE:
  agent: monitoring-automation
  lane: kucoin
  generated_at: {now}
  source: scripts/monitoring_automation.py
  type: {window.period}-analysis

# KuCoin Monitoring {window.period.title()} Analysis

- Window start (UTC): `{iso_utc(window.start)}`
- Window end (UTC): `{iso_utc(window.end)}`
- Total rows in history file: `{row_count}`
- Rows in window: `{summary["samples"]}`

## Availability
- SESSION_STATE present: `{fmt_pct(summary["session_exists_pct"])}`
- Heartbeat present: `{fmt_pct(summary["heartbeat_exists_pct"])}`

## Runtime Trends
- Status counts: `{statuses}`
- Phase counts: `{phases}`
- Final=true ratio: `{fmt_pct(summary["final_true_pct"])}`

## Service Topology
- KuCoin unit seen ratio: `{fmt_pct(summary["kucoin_unit_seen_pct"])}`
- Governance unit average: `{summary["governance_unit_avg"]:.2f}`

## Cadence
- Snapshot interval: `{interval_text}`
"""


def write_analysis(period: str) -> Path:
    rows = parse_history()
    window = select_window(period)
    selected = in_window(rows, window)
    summary = summarize(selected)

    ts_file = iso_utc(utc_now()).replace(":", "-")
    report = render_analysis_markdown(window, summary, row_count=len(rows))
    report_path = DOCS_DIR / f"MONITORING_ANALYSIS_{period}_{ts_file}.md"
    write_text(report_path, report)
    write_text(DOCS_DIR / f"latest-monitoring-analysis-{period}.md", report)
    return report_path


def cmd_snapshot() -> None:
    ensure_dirs()
    snapshot = collect_snapshot()
    append_history(snapshot)
    snapshot_path = write_snapshot_artifacts(snapshot)
    print(json.dumps({
        "result": "ok",
        "action": "snapshot",
        "timestamp_utc": snapshot["timestamp_utc"],
        "history_path": str(HISTORY_JSONL),
        "snapshot_path": str(snapshot_path),
    }, indent=2))


def cmd_analyze(period: str) -> None:
    ensure_dirs()
    report_path = write_analysis(period)
    print(json.dumps({
        "result": "ok",
        "action": "analyze",
        "period": period,
        "report_path": str(report_path),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="KuCoin monitoring automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("snapshot", help="Capture hourly monitoring snapshot")

    analyze_parser = subparsers.add_parser("analyze", help="Generate periodic analysis")
    analyze_parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly"],
        required=True,
        help="Analysis window",
    )

    args = parser.parse_args()
    if args.command == "snapshot":
        cmd_snapshot()
    elif args.command == "analyze":
        cmd_analyze(args.period)
    else:
        raise RuntimeError("Unsupported command")


if __name__ == "__main__":
    main()
