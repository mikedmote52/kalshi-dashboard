#!/usr/bin/env python3
"""
publish_dashboard_data.py
Exports data from the Kalshi prediction bot's SQLite database,
writes dashboard_data.json, and pushes to GitHub Pages.

Usage:
    python3 publish_dashboard_data.py              # Export + push
    python3 publish_dashboard_data.py --export-only # Export only, no git push

Connects to the bot at ~/Desktop/kalshi-bot/kalshi_predictor.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
BOT_DIR = Path.home() / "Desktop" / "kalshi-bot"
BOT_SCRIPT = BOT_DIR / "kalshi_predictor.py"
OUTPUT = REPO_DIR / "dashboard_data.json"


def run(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd or REPO_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ! {' '.join(cmd)}\n    {result.stderr.strip()}")
    return result.returncode == 0


def main():
    export_only = "--export-only" in sys.argv
    print("=== Kalshi Dashboard Publisher ===")
    print(f"    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Step 1: Run the bot's export-dashboard command
    print("Exporting from bot database...")
    if BOT_SCRIPT.exists():
        result = subprocess.run(
            ["python3", str(BOT_SCRIPT), "export-dashboard", str(OUTPUT)],
            capture_output=True, text=True, cwd=str(BOT_DIR)
        )
        if result.returncode == 0:
            print(f"  OK: {result.stdout.strip()}")
        else:
            print(f"  ! Export failed: {result.stderr.strip()}")
            # Write empty state so dashboard still loads
            with open(OUTPUT, "w") as f:
                json.dump({
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "balance": 100.00,
                    "total_pnl": 0,
                    "positions": [],
                    "latest_scan": None,
                    "opportunities": [],
                    "trade_history": [],
                    "performance": None,
                }, f, indent=2)
            print("  Wrote empty dashboard_data.json as fallback")
    else:
        print(f"  ! Bot not found at {BOT_SCRIPT}")
        print("    Make sure kalshi-bot is on your Desktop")
        return

    if export_only:
        print(f"\n  Exported to {OUTPUT}")
        return

    # Step 2: Push to GitHub Pages
    print("\nPublishing to GitHub Pages...")
    if not run(["git", "add", "dashboard_data.json", "index.html"]):
        sys.exit(1)

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO_DIR, capture_output=True
    )
    if status.returncode == 0:
        print("  No changes to publish")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not run(["git", "commit", "-m", f"update dashboard {ts}"]):
        sys.exit(1)

    if not run(["git", "push"]):
        sys.exit(1)

    print("\nDashboard published.")
    print("  https://mikedmote52.github.io/kalshi-dashboard/")


if __name__ == "__main__":
    main()
