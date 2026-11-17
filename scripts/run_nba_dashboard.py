#!/usr/bin/env python3
"""Run local MBM NBA analyst dashboard on synthetic/demo envelopes."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.analyst.assembly import build_dashboard_snapshot  # noqa: E402
from mbm.analyst.cs2_bridge import decide_headshots  # noqa: E402
from mbm.analyst.nba_bridge import decide_nba_prop  # noqa: E402
from mbm.dashboard.app import serve_dashboard  # noqa: E402
from mbm.dashboard.nba import assemble_nba_snapshot  # noqa: E402
from mbm.providers.balldontlie.pipeline import refresh_from_synthetic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MBM NBA analyst dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=ROOT / "fixtures" / "balldontlie" / "synthetic" / "ok",
    )
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    now = datetime(2025, 11, 15, 1, 0, 0, tzinfo=timezone.utc)
    env = refresh_from_synthetic(
        args.synthetic_dir,
        target_player_id="237",
        line=27.5,
        prop_stat="points",
    )
    # Persist normalized demo for discoverability
    demo = ROOT / "fixtures" / "nba" / "demo_prop"
    demo.mkdir(parents=True, exist_ok=True)
    (demo / "normalized.json").write_text(
        __import__("json").dumps(env.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )

    nba_snap = assemble_nba_snapshot(
        [("nba-demo-910001", env)],
        decide_nba_prop,
        data_label="nba-synthetic/demo",
        now=now,
    )
    # Keep CS2 board available on / for shared server.
    cs2_snap = build_dashboard_snapshot(
        ROOT / "fixtures" / "cs2",
        lambda e: decide_headshots(e, now=datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc)),
        data_label="fixture/demo",
        now=datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc),
    )

    try:
        server = serve_dashboard(
            cs2_snap, host=args.host, port=args.port, nba_snapshot=nba_snap
        )
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}/nba"
    print("MBM NBA analyst dashboard", flush=True)
    print(f"  URL:   {url}", flush=True)
    print(f"  Data:  {nba_snap.data_label}", flush=True)
    print(f"  Core:  {nba_snap.core_status}", flush=True)
    print(f"  Board: {len(nba_snap.board)} picks", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
