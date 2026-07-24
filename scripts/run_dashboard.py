#!/usr/bin/env python3
"""Run the local MBM Esports analyst dashboard on fixture/demo data."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.analyst.assembly import build_dashboard_snapshot  # noqa: E402
from mbm.analyst.cs2_bridge import decide_headshots  # noqa: E402
from mbm.dashboard.app import serve_dashboard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MBM Esports analyst dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=ROOT / "fixtures" / "cs2",
        help="Directory of recorded CS2 evidence fixtures",
    )
    args = parser.parse_args()

    now = datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc)

    def decide(envelope):
        return decide_headshots(envelope, now=now)

    snapshot = build_dashboard_snapshot(
        args.fixtures,
        decide,
        data_label="fixture/demo",
        now=now,
    )
    server = serve_dashboard(snapshot, host=args.host, port=args.port)
    print(f"MBM Esports analyst dashboard")
    print(f"  URL:   http://{args.host}:{args.port}/")
    print(f"  Data:  {snapshot.data_label}")
    print(f"  Core:  {snapshot.core_status}")
    print(f"  Board: {len(snapshot.board)} picks")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
