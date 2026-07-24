#!/usr/bin/env python3
"""Manual BO3.gg refresh (optional live smoke) or synthetic offline normalize.

Live mode uses an honest MBM-esports User-Agent only — no browser impersonation.
On non-200 / non-JSON: records BO3 unavailable and stops (no retries).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.providers.bo3gg.client import Bo3Client, USER_AGENT  # noqa: E402
from mbm.providers.bo3gg.pipeline import refresh_from_synthetic, refresh_live_smoke  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh BO3.gg evidence into intake")
    parser.add_argument(
        "--mode",
        choices=("synthetic", "live"),
        default="synthetic",
        help="synthetic=unit fixtures; live=one-shot honest HTTP to api.bo3.gg",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=ROOT / "fixtures" / "bo3gg" / "synthetic" / "ok",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "intake" / "raw",
        help="Live raw BO3 payloads land under <out-dir>/bo3gg/",
    )
    parser.add_argument("--team-query", default=None)
    parser.add_argument("--line", type=float, default=None)
    parser.add_argument("--player-id", default=None)
    args = parser.parse_args()

    if args.mode == "synthetic":
        env = refresh_from_synthetic(
            args.synthetic_dir,
            out_dir=ROOT / "fixtures" / "bo3gg",
            target_player_id=args.player_id,
            line=args.line,
        )
        print("mode=synthetic (not_for_projection)")
    else:
        print(f"mode=live User-Agent={USER_AGENT}")
        client = Bo3Client()
        env = refresh_live_smoke(client, out_dir=args.out_dir, team_query=args.team_query)

    print(json.dumps(
        {
            "source": env.source,
            "event_id": env.fixture.event_id,
            "teams": [env.fixture.team_a, env.fixture.team_b],
            "evidence_status": env.evidence_status.value,
            "not_for_projection": env.map_context.get("not_for_projection"),
            "source_attempts": [a.__dict__ for a in env.source_attempts],
            "pass_reasons": next(
                (p.value for p in env.provenance if p.name == "pass_reasons"),
                None,
            ),
        },
        indent=2,
        default=str,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
