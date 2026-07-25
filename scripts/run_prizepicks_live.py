#!/usr/bin/env python3
"""Serve locked PrizePicks capture routes (browser bridge only; no scoring)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.live.prizepicks_http import (  # noqa: E402
    PATH_CAPTURE,
    PATH_HEALTH,
    PATH_HISTORY,
    PATH_LATEST,
    serve_prizepicks,
)
from mbm.providers.prizepicks.service import PrizePicksCaptureService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MBM PrizePicks live capture API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "intake" / "raw" / "prizepicks",
        help="Append-only snapshot root (gitignored)",
    )
    parser.add_argument(
        "--bridge-token",
        default=os.environ.get("MBM_BRIDGE_TOKEN"),
        help="Required X-MBM-Bridge-Token value (or env MBM_BRIDGE_TOKEN)",
    )
    args = parser.parse_args()

    service = PrizePicksCaptureService(args.data_dir, bridge_token=args.bridge_token)
    server = serve_prizepicks(service, host=args.host, port=args.port)
    print("MBM PrizePicks live capture")
    print(f"  URL:     http://{args.host}:{args.port}/")
    print(f"  Data:    {args.data_dir}")
    print(f"  POST     {PATH_CAPTURE}")
    print(f"  GET      {PATH_LATEST}")
    print(f"  GET      {PATH_HISTORY}")
    print(f"  GET      {PATH_HEALTH}")
    print("  scoring: untouched (scoring_touched=false)")
    if args.bridge_token:
        print("  auth:    X-MBM-Bridge-Token required")
    else:
        print("  auth:    bridge token not set (open local mode)")
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
