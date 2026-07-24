#!/usr/bin/env python3
"""Manual OddsPapi refresh (optional live smoke) or synthetic offline normalize.

Live mode uses an honest MBM-esports User-Agent only — no browser impersonation.
Auth via ODDSPAPI_API_KEY (never commit keys). On non-200 / non-JSON: records
OddsPapi unavailable and stops (no retries). Stored URLs redact apiKey.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.providers.oddspapi.client import (  # noqa: E402
    API_KEY_ENV,
    OddsPapiClient,
    USER_AGENT,
)
from mbm.providers.oddspapi.pipeline import (  # noqa: E402
    refresh_from_synthetic,
    refresh_live_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh OddsPapi evidence into intake")
    parser.add_argument(
        "--mode",
        choices=("synthetic", "live"),
        default="synthetic",
        help="synthetic=unit fixtures; live=one-shot honest HTTP to v5.oddspapi.io",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=ROOT / "fixtures" / "oddspapi" / "synthetic" / "ok",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "intake" / "raw",
        help="Live raw OddsPapi payloads land under <out-dir>/oddspapi/",
    )
    parser.add_argument("--tournament-id", type=int, default=None)
    parser.add_argument("--bookmakers", default="pinnacle")
    parser.add_argument("--line", type=float, default=None)
    parser.add_argument("--player-id", default=None)
    args = parser.parse_args()

    if args.mode == "synthetic":
        env = refresh_from_synthetic(
            args.synthetic_dir,
            out_dir=ROOT / "fixtures" / "oddspapi",
            target_player_id=args.player_id,
            line=args.line,
        )
        print("mode=synthetic (not_for_projection)")
    else:
        print(f"mode=live User-Agent={USER_AGENT} auth_env={API_KEY_ENV}")
        client = OddsPapiClient()
        env = refresh_live_smoke(
            client,
            out_dir=args.out_dir,
            tournament_id=args.tournament_id,
            bookmakers=args.bookmakers,
        )

    print(
        json.dumps(
            {
                "source": env.source,
                "event_id": env.fixture.event_id,
                "teams": [env.fixture.team_a, env.fixture.team_b],
                "evidence_status": env.evidence_status.value,
                "market_lines": [m.__dict__ for m in env.market_lines],
                "not_for_projection": env.map_context.get("not_for_projection"),
                "source_attempts": [a.__dict__ for a in env.source_attempts],
                "pass_reasons": next(
                    (p.value for p in env.provenance if p.name == "pass_reasons"),
                    None,
                ),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
