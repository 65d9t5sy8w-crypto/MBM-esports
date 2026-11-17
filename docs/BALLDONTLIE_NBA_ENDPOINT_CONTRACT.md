# BallDontLie NBA endpoint contract

Base URL: `https://api.balldontlie.io`

OpenAPI source (vendored): [`vendor/balldontlie/nba.yml`](../vendor/balldontlie/nba.yml)
Upstream: `https://www.balldontlie.io/openapi/nba.yml`

Adapter class: `BallDontLieNbaAdapter`.

## Verified access (probed 2026-11-17)

| Path | Docs tier | Probe result | Production status |
|------|-----------|--------------|-------------------|
| `GET /nba/v1/teams` | Free | HTTP 200 | **Enabled** |
| `GET /nba/v1/teams/{id}` | Free | (same catalog) | **Enabled** |
| `GET /nba/v1/players` | Free | HTTP 200 | **Enabled** |
| `GET /nba/v1/players/{id}` | Free | (same catalog) | **Enabled** |
| `GET /nba/v1/games` | Free | HTTP 200 | **Enabled** |
| `GET /nba/v1/games/{id}` | Free | (same catalog) | **Enabled** |
| `GET /nba/v1/stats` | ALL-STAR | HTTP 401 | **Disabled** |
| `GET /nba/v1/players/active` | ALL-STAR | HTTP 401 | **Disabled** |
| `GET /nba/v1/player_injuries` | ALL-STAR | HTTP 401 | **Disabled** |
| `GET /nba/v2/odds` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v2/odds/player_props` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v2/stats/advanced` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v1/lineups` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v1/projected_lineups` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v1/box_scores` | GOAT | HTTP 401 | **Disabled** |
| `GET /nba/v1/standings` | GOAT | HTTP 401 | **Disabled** |
| Remaining OpenAPI `/nba/*` GOAT paths | GOAT | not re-probed after 401 pattern | **Disabled** |

Paid / unverified endpoints return an unavailable result **without** contacting the network.

## Client policy

- Auth: `Authorization` header from `BALLDONTLIE_API_KEY` (OpenAPI `ApiKeyAuth`).
- Honest User-Agent only: `MBM-esports/<version> (+repo)`.
- Never place API keys in query strings, logs, raw intake metadata, or evidence files.
- Unit tests use **synthetic** fixtures under `fixtures/balldontlie/synthetic/` only.
- Live smoke (FREE only): `scripts/refresh_balldontlie.py --mode live`.

## Evidence honesty

| Kind | Label | Location |
|------|-------|----------|
| Hand-authored unit fixtures | `source=synthetic_test_fixture`, `captured_at=null`, `not_for_projection=true` | `fixtures/balldontlie/synthetic/` |
| Live FREE responses | `source=balldontlie` | `intake/raw/balldontlie/` |

Never label synthetic JSON as BallDontLie recorded evidence.

## Leakage / walk-forward (hard rules)

1. Features, lines, injuries, and market snapshots must be knowable **before** tip-off (`PointInTimeCutoff.as_of`).
2. Settlement labels are never model inputs.
3. Chronological walk-forward only — never shuffle across time.
4. Purging uses the **entire** feature/label window (`valid_from`→`valid_to`), not game date alone.
5. Hyperparameter tuning uses only **earlier** validation folds.
6. Each backtest row carries an audit record: prediction timestamp, model version, source snapshot IDs, sportsbook price, settlement outcome.

**Certification: PENDING** until the leakage/walk-forward suite passes and paid access (if needed) is verified.
