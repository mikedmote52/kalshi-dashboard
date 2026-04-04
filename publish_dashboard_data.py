#!/usr/bin/env python3
"""
publish_dashboard_data.py
Reads live data from the Intelligence Bridge and publishes it to the
kalshi-dashboard repo as dashboard_data.json, then git commits and pushes.

Run manually or wire into a cron / launchd schedule.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
UNIFIED_FEED = Path.home() / "Desktop/intelligence-bridge/bridge-status/unified_feed.json"
NARRATIVE_SIGNALS = Path.home() / "Desktop/intelligence-bridge/sentinel/narrative_signals.json"
THESIS_DASHBOARD = Path.home() / "Desktop/claude kalshi/data/thesis_dashboard.json"
OUTPUT = REPO_DIR / "dashboard_data.json"


def read_json(path: Path, label: str):
    try:
        with open(path) as f:
            data = json.load(f)
        print(f"  ✓ {label}")
        return data
    except FileNotFoundError:
        print(f"  ✗ {label} — not found, skipping")
        return None
    except json.JSONDecodeError as e:
        print(f"  ✗ {label} — JSON parse error: {e}")
        return None


def run(cmd: list[str], cwd=None):
    result = subprocess.run(cmd, cwd=cwd or REPO_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ! {' '.join(cmd)}\n    {result.stderr.strip()}")
    return result.returncode == 0


def main():
    print("=== Kalshi Dashboard Publisher ===")
    print(f"    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    print("Reading source data...")
    unified_feed = read_json(UNIFIED_FEED, "unified_feed.json")
    narrative_signals = read_json(NARRATIVE_SIGNALS, "narrative_signals.json")
    thesis_dashboard = read_json(THESIS_DASHBOARD, "thesis_dashboard.json")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unified_feed": unified_feed,
        "narrative_signals": narrative_signals,
        "thesis_dashboard": thesis_dashboard,
    }

    print(f"\nWriting {OUTPUT.name}...")
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  ✓ {OUTPUT}")

    print("\nPublishing to GitHub Pages...")
    if not run(["git", "add", "dashboard_data.json"]):
        sys.exit(1)

    # Check if there are staged changes before committing
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO_DIR, capture_output=True
    )
    if status.returncode == 0:
        print("  — No changes to publish (data unchanged)")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not run(["git", "commit", "-m", f"chore: publish dashboard data {ts}"]):
        sys.exit(1)

    if not run(["git", "push"]):
        sys.exit(1)

    print("\n✓ Dashboard data published successfully.")
    print("  Live at: https://mikedmote52.github.io/kalshi-dashboard/")


if __name__ == "__main__":
    main()
