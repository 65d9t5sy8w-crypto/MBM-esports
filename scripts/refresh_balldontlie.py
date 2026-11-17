#!/usr/bin/env python3
"""Manual BallDontLie NBA refresh (optional live smoke) or synthetic offline normalize.

Live mode calls only verified FREE endpoints. Paid endpoints stay disabled.
Auth via BALLDONTLIE_API_KEY (Authorization header). Never commit keys;
stored URLs never include credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.providers.balldontlie.client import (  # noqa: E402
    API_KEY_ENV,
    USER_AGENT,
    BallDontLieNbaAdapter,
)
from mbm.providers.balldontlie.pipeline import (  # noqa: E402
    refresh_from_synthetic,
    refresh_live_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh BallDontLie NBA evidence")
    parser.add_argument("--mode", choices=("synthetic", "live"), default="synthetic")
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=ROOT / "fixtures" / "balldontlie" / "synthetic" / "ok",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "intake" / "raw")
    parser.add_argument("--player-id", default="237")
    parser.add_argument("--line", type=float, default=27.5)
    parser.add_argument("--prop-stat", default="points")
    args = parser.parse_args()

    if args.mode == "synthetic":
        env = refresh_from_synthetic(
            args.synthetic_dir,
            out_dir=ROOT / "fixtures" / "balldontlie",
            target_player_id=args.player_id,
            line=args.line,
            prop_stat=args.prop_stat,
        )
        print("mode=synthetic (not_for_projection)")
    else:
        print(f"mode=live User-Agent={USER_AGENT} auth_env={API_KEY_ENV}")
        adapter = BallDontLieNbaAdapter()
        env = refresh_live_smoke(adapter, out_dir=args.out_dir)

    print(
        json.dumps(
            {
                "source": env.source,
                "event_id": env.fixture.event_id,
                "teams": [env.fixture.team_a, env.fixture.team_b],
                "evidence_status": env.evidence_status.value,
                "not_for_projection": env.map_context.get("not_for_projection"),
                "sportsbook_price_count": len(env.map_context.get("sportsbook_prices") or []),
                "stats_count": env.map_context.get("stats_count"),
                "source_attempts": [a.__dict__ for a in env.source_attempts],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
