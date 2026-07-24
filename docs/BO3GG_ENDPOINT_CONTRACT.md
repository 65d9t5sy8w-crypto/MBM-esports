# BO3.gg endpoint contract

Base URL: `https://api.bo3.gg/api/v1`

Mapped from the public CS2API wrapper reference ([tommhe14/CS2API](https://github.com/tommhe14/CS2API)).
Provider-specific shapes stay in `mbm/providers/bo3gg/`; canonical modules consume
`EvidenceEnvelope` only.

## Client policy

- Honest User-Agent only: `MBM-esports/<version> (+repo)`.
- **Do not** send fake Chrome, `sec-ch-ua`, `Origin`, or `Referer` headers.
- **Do not** impersonate a browser or attempt to bypass provider controls.
- One request per call; on non-200 or non-JSON: record unavailable and stop (no retry loop).
- Unit tests use **synthetic** fixtures under `fixtures/bo3gg/synthetic/` only.
- Live calls are optional via `scripts/refresh_bo3gg.py`.

## Evidence honesty

| Kind | Label | Location |
|------|-------|----------|
| Hand-authored unit fixtures | `source=synthetic_test_fixture`, `captured_at=null`, `not_for_projection=true` | `fixtures/bo3gg/synthetic/` |
| Byte-for-byte BO3.gg responses | `source=bo3.gg` | `intake/raw/bo3gg/` (or live out dir under `*/bo3gg/`) |

Never label synthetic JSON as BO3 recorded evidence.

## Endpoints used by MBM-esports

| Purpose | Method | Path | Key query params |
|---------|--------|------|------------------|
| Upcoming matches | GET | `/matches` | `scope=widget-matches`, status `upcoming`, discipline `1` |
| Live / current matches | GET | `/matches` | status `current` |
| Finished matches | GET | `/matches` | status `finished` |
| Match detail | GET | `/matches/{slug}` | `scope=show-match` |
| Player match history | GET | `/matches` | `filter[matches.player_ids][overlap]` |
| Team search | GET | `/filters/teams` | `search_text` |

## Evidence rules

- Preserve raw response bytes beside normalized records **only** for live BO3 payloads.
- Always set ISO-8601 `captured_at` on live BO3 evidence.
- Failures become explicit PASS reasons via the source-attempt ledger (never generic “data unavailable”).
- Core eligibility remains BLOCKED until the authentic wheel is vendored.
