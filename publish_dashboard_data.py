#!/usr/bin/env python3
"""
publish_dashboard_data.py
Reads live data from the Intelligence Bridge and publishes it to the
kalshi-dashboard repo as dashboard_data.json, then git commits and pushes.

Also reads approvals.json for UI decisions and can sync them back to the DB.

Run manually or wire into a cron / launchd schedule.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REPO_DIR = Path(__file__).parent.resolve()
UNIFIED_FEED = Path.home() / "Desktop/intelligence-bridge/bridge-status/unified_feed.json"
NARRATIVE_SIGNALS = Path.home() / "Desktop/intelligence-bridge/sentinel/narrative_signals.json"
THESIS_DASHBOARD = Path.home() / "Desktop/claude kalshi/data/thesis_dashboard.json"
APPROVALS_FILE = REPO_DIR / "approvals.json"
OUTPUT = REPO_DIR / "dashboard_data.json"

# DB connection — Docker exposes Postgres on localhost:5432
DB_URL = "postgresql://user:pass@localhost:5432/market_intel"

# Sample pending approvals — shown when no live DB data is available.
SAMPLE_PENDING_APPROVALS = [
    {
        "id": "th-001",
        "thesis_summary": (
            "EU counter-tariff vote likely before April 15 — Kalshi market (66¢) underprices "
            "passage probability given EC committee composition and Liberation Day political pressure. "
            "EC has history of rapid retaliation votes within 10 days of U.S. tariff announcements."
        ),
        "cascade_chain": ["geo", "trade_policy", "macro"],
        "instrument": "kxforeigntariff/retaliatory-tariffs",
        "proposed_size": 8,
        "kelly_quarter": 5,
        "direction": "YES",
        "confidence": 0.72,
    },
    {
        "id": "th-002",
        "thesis_summary": (
            "Fed has no runway to cut before Q2 end. Three governor speeches confirm hold. "
            "Inflation sticky at 3.1%. Market at 22¢ still overpricing a cut — consensus requires "
            "3 consecutive months below 2.5%, unachievable by July under current trajectory."
        ),
        "cascade_chain": ["macro", "finance"],
        "instrument": "kxratecut/fed-rate-cut/kxratecut-26dec31",
        "proposed_size": 10,
        "kelly_quarter": 6,
        "direction": "NO",
        "confidence": 0.65,
    },
    {
        "id": "th-003",
        "thesis_summary": (
            "PLA strait exercises correlate with rhetorical escalation phase, not kinetic precursor. "
            "Xi economic focus constrains military adventurism during tariff war — historical pattern "
            "shows PLA exercises de-escalate within 30 days when trade tensions dominate Beijing's agenda."
        ),
        "cascade_chain": ["geo", "defense", "energy"],
        "instrument": "kxxitaiwan/will-xi-jinping-visit-taiwan/kxxitaiwan",
        "proposed_size": 7,
        "kelly_quarter": 4,
        "direction": "YES",
        "confidence": 0.58,
    },
]


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


def run(cmd: List[str], cwd=None):
    result = subprocess.run(cmd, cwd=cwd or REPO_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ! {' '.join(cmd)}\n    {result.stderr.strip()}")
    return result.returncode == 0


def ensure_approvals_file():
    """Create approvals.json with an empty array if it doesn't exist."""
    if not APPROVALS_FILE.exists():
        with open(APPROVALS_FILE, "w") as f:
            json.dump([], f, indent=2)
        print(f"  ✓ Created {APPROVALS_FILE.name} (empty)")
    else:
        print(f"  ✓ {APPROVALS_FILE.name} exists")


def read_approvals() -> list:
    """Read UI decisions from approvals.json."""
    try:
        with open(APPROVALS_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            approved = [e for e in data if e.get("status") == "approved"]
            rejected = [e for e in data if e.get("status") == "rejected"]
            print(f"  ✓ approvals.json — {len(approved)} approved, {len(rejected)} rejected")
            return data
        return []
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        print(f"  ✗ approvals.json — JSON parse error: {e}")
        return []


def fetch_pending_from_db() -> Optional[List]:
    """Read pending/active theses from Postgres and format for the dashboard."""
    try:
        import psycopg2  # type: ignore
        import os

        conn_str = os.environ.get("KALSHI_DB_URL", DB_URL)
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()

        # Fetch active and pending theses with their opportunity instrument data
        cur.execute(
            """
            SELECT
                tr.id,
                tr.thesis_summary,
                tr.cascade_chain,
                tr.probability_estimate,
                tr.status,
                tr.health_score,
                aq.proposed_size,
                aq.kelly_fraction,
                aq.proposed_action,
                aq.status as approval_status,
                aq.proposed_instrument
            FROM thesis_records tr
            LEFT JOIN approval_queue aq ON aq.thesis_id = tr.id
            
            WHERE tr.status IN ('proposed', 'active', 'degraded')
            ORDER BY tr.created_at DESC
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        results = []
        for i, row in enumerate(rows):
            raw_inst = row[10] or "unknown"
            instrument_id = raw_inst.split(":", 1)[-1] if ":" in str(raw_inst) else str(raw_inst)
            direction = (row[8] or "buy").upper()

            results.append({
                "id": f"th-{i+1:03d}",
                "thesis_id": str(row[0]),
                "thesis_summary": row[1] or "",
                "cascade_chain": row[2] if isinstance(row[2], list) else [],
                "instrument": instrument_id,
                "proposed_size": float(row[6]) if row[6] else 8,
                "kelly_quarter": str(row[7]) if row[7] else "1/4 Kelly",
                "direction": direction,
                "confidence": float(row[3]) if row[3] else 0.5,
                "status": row[4],
                "health_score": float(row[5]) if row[5] else 100,
                "approval_status": row[9] or "pending",
            })

        return results if results else None
    except Exception as e:
        print(f"  ! DB query failed: {e}")
        return None


def write_decisions_to_db(approvals: list) -> None:
    """
    Write UI approval decisions back to the approval_queue table.
    No-op if DB is not accessible.
    """
    if not approvals:
        return
    try:
        import psycopg2  # type: ignore
        import os

        conn_str = os.environ.get("KALSHI_DB_URL")
        if not conn_str:
            return

        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        for entry in approvals:
            cur.execute(
                """
                UPDATE approval_queue
                SET status = %s, approved_amount = %s, decided_at = NOW()
                WHERE id = %s AND status = 'pending'
                """,
                (entry.get("status"), entry.get("amount"), entry.get("id")),
            )
        conn.commit()
        cur.close()
        conn.close()
        print(f"  ✓ Synced {len(approvals)} decision(s) to DB")
    except Exception as e:
        print(f"  ! DB write skipped: {e}")


def main():
    print("=== Kalshi Dashboard Publisher ===")
    print(f"    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Ensure approvals.json exists
    print("Checking approvals file...")
    ensure_approvals_file()

    # Read UI decisions and optionally sync to DB
    print("\nReading UI decisions...")
    approvals = read_approvals()
    if approvals:
        write_decisions_to_db(approvals)

    # Fetch pending approvals (DB → sample fallback)
    print("\nFetching pending approvals...")
    pending_approvals = fetch_pending_from_db()
    if pending_approvals is not None:
        print(f"  ✓ DB — {len(pending_approvals)} pending trade(s)")
        # Filter out any already decided by the UI
        decided_ids = {e["id"] for e in approvals}
        pending_approvals = [p for p in pending_approvals if p["id"] not in decided_ids]
    else:
        print("  — DB not available, using sample pending approvals")
        decided_ids = {e["id"] for e in approvals}
        pending_approvals = [p for p in SAMPLE_PENDING_APPROVALS if p["id"] not in decided_ids]

    # Read intelligence data
    print("\nReading source data...")
    unified_feed = read_json(UNIFIED_FEED, "unified_feed.json")
    narrative_signals = read_json(NARRATIVE_SIGNALS, "narrative_signals.json")
    thesis_dashboard = read_json(THESIS_DASHBOARD, "thesis_dashboard.json")

    # Inject live pending approvals into thesis_dashboard
    if thesis_dashboard is None:
        thesis_dashboard = {}
    thesis_dashboard["pending_approvals"] = pending_approvals

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
    if not run(["git", "add", "dashboard_data.json", "approvals.json"]):
        sys.exit(1)

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
