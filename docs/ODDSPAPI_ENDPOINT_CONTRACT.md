# OddsPapi endpoint contract

Base URL: `https://v5.oddspapi.io/en`

Mapped from the public OddsPapi v5 REST docs ([docs.oddspapi.io](https://docs.oddspapi.io/llms.txt)).
Provider-specific shapes stay in `mbm/providers/oddspapi/`; canonical modules consume
`EvidenceEnvelope` only.

CS2 sport id: **17** (`ESport Counter-Strike`).

## Client policy

- Honest User-Agent only: `MBM-esports/<version> (+repo)`.
- **Do not** send fake Chrome, `sec-ch-ua`, `Origin`, or `Referer` headers.
- Auth: `apiKey` query parameter from env `ODDSPAPI_API_KEY` (or constructor).
- **Never** commit API keys, cookies, or session tokens.
- Redact `apiKey` from any URL written to raw intake or logs.
- One request per call; on non-200 or non-JSON: record unavailable and stop (no retry loop).
- Unit tests use **synthetic** fixtures under `fixtures/oddspapi/synthetic/` only.
- Live calls are optional via `scripts/refresh_oddspapi.py --mode live`.

## Evidence honesty

| Kind | Label | Location |
|------|-------|----------|
| Hand-authored unit fixtures | `source=synthetic_test_fixture`, `captured_at=null`, `not_for_projection=true` | `fixtures/oddspapi/synthetic/` |
| Byte-for-byte OddsPapi responses | `source=oddspapi` | `intake/raw/oddspapi/` (or live out dir under `*/oddspapi/`) |

Never label synthetic JSON as OddsPapi recorded evidence.

## Endpoints used by MBM-esports

| Purpose | Method | Path | Key query params |
|---------|--------|------|------------------|
| Sports catalog | GET | `/sports` | — |
| CS2 tournaments | GET | `/tournaments` | `sportId=17` |
| CS2 fixtures | GET | `/fixtures` | `sportId=17` (optional `tournamentId`, `bookmakers`) |
| Fixture odds | GET | `/fixtures/odds` | `fixtureId`, optional `bookmakers`, `mainLine` |
| Participants | GET | `/participants` | `sportId=17` or `participantIds` |
| Players | GET | `/players` | `sportId=17` / `participantId` / `playerIds` |
| Markets catalog | GET | `/markets` | optional filters |

All requests also require `apiKey`.

## Evidence rules

- Preserve raw response bytes beside normalized records **only** for live OddsPapi payloads.
- Always set ISO-8601 `captured_at` on live OddsPapi evidence.
- Failures become explicit PASS reasons via the source-attempt ledger (never generic “data unavailable”).
- OddsPapi supplies **market board / odds**, not CS2 match logs. Headshots gates still need
  Mason-supplied (or other) Maps 1–2 logs before Core-backed projection.
- Core eligibility remains BLOCKED until the authentic wheel is vendored.
