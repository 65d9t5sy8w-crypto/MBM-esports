#!/usr/bin/env python3
"""Manual OddsPapi v4 refresh (optional live smoke) or synthetic offline normalize.

Live mode uses an honest MBM-esports User-Agent only — no browser impersonation.
Auth via ODDSPAPI_API_KEY (never commit keys). Calls only verified /v4 endpoints.
On non-200 / non-JSON: records OddsPapi unavailable and stops (no retries).
Stored URLs redact apiKey.
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
    SPORT_ID_CS2,
    SPORT_ID_LOL,
    SPORT_ID_VALORANT,
    USER_AGENT,
    OddsPapiV4Adapter,
)
from mbm.providers.oddspapi.pipeline import (  # noqa: E402
    refresh_from_synthetic,
    refresh_live_smoke,
)

_SPORT_CHOICES = {
    "cs2": SPORT_ID_CS2,
    "lol": SPORT_ID_LOL,
    "valorant": SPORT_ID_VALORANT,
    str(SPORT_ID_CS2): SPORT_ID_CS2,
    str(SPORT_ID_LOL): SPORT_ID_LOL,
    str(SPORT_ID_VALORANT): SPORT_ID_VALORANT,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh OddsPapi v4 evidence into intake")
    parser.add_argument(
        "--mode",
        choices=("synthetic", "live"),
        default="synthetic",
        help="synthetic=unit fixtures; live=one-shot honest HTTP to api.oddspapi.io/v4",
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
    parser.add_argument(
        "--sport",
        default="cs2",
        help="Verified esports sport: cs2|lol|valorant or sportId 17|18|61",
    )
    parser.add_argument("--tournament-ids", default=None, help="Comma-separated tournament ids")
    parser.add_argument("--bookmaker", default="pinnacle")
    parser.add_argument("--line", type=float, default=None)
    parser.add_argument("--player-id", default=None)
    args = parser.parse_args()

    sport_key = str(args.sport).strip().lower()
    if sport_key not in _SPORT_CHOICES:
        raise SystemExit(
            f"unsupported sport {args.sport!r}; use one of {sorted(_SPORT_CHOICES)}"
        )
    sport_id = _SPORT_CHOICES[sport_key]

    if args.mode == "synthetic":
        env = refresh_from_synthetic(
            args.synthetic_dir,
            out_dir=ROOT / "fixtures" / "oddspapi",
            target_player_id=args.player_id,
            line=args.line,
            sport_id=sport_id,
        )
        print("mode=synthetic (not_for_projection)")
    else:
        print(f"mode=live User-Agent={USER_AGENT} auth_env={API_KEY_ENV} sport_id={sport_id}")
        adapter = OddsPapiV4Adapter()
        tournament_ids = None
        if args.tournament_ids:
            tournament_ids = [x.strip() for x in args.tournament_ids.split(",") if x.strip()]
        env = refresh_live_smoke(
            adapter,
            out_dir=args.out_dir,
            sport_id=sport_id,
            tournament_ids=tournament_ids,
            bookmaker=args.bookmaker,
        )

    print(
        json.dumps(
            {
                "source": env.source,
                "event_id": env.fixture.event_id,
                "teams": [env.fixture.team_a, env.fixture.team_b],
                "evidence_status": env.evidence_status.value,
                "sport_id": env.map_context.get("sport_id"),
                "api_version": env.map_context.get("api_version"),
                "pinnacle_price_count": len(env.map_context.get("pinnacle_prices") or []),
                "player_prop_claim": env.map_context.get("player_prop_claim"),
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
