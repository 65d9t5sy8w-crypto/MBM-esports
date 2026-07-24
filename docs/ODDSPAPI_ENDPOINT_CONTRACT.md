# OddsPapi v4 endpoint contract

Base URL: `https://api.oddspapi.io`

Locked MBM integration is **OddsPapi v4 only**. Provider-specific shapes stay in
`mbm/providers/oddspapi/`; canonical modules consume `EvidenceEnvelope` only.

Adapter class: `OddsPapiV4Adapter`.

## Verified production endpoints

| Purpose | Method | Path | Key query params |
|---------|--------|------|------------------|
| Sports catalog | GET | `/v4/sports` | `apiKey` |
| Tournaments by sport | GET | `/v4/tournaments` | `sportId`, `language`, `apiKey` |
| Odds by tournaments | GET | `/v4/odds-by-tournaments` | `tournamentIds`, `bookmaker`, `apiKey` |

No other OddsPapi paths are authorized for production intake.

## Verified esports sport IDs

| Title | sportId |
|-------|--------:|
| CS2 (ESport Counter-Strike) | 17 |
| LoL (ESport League of Legends) | 18 |
| VALORANT | 61 |

The adapter is **not** CS2-only. Callers must pass an explicit verified `sport_id`.

## Unsupported license boundary (OddsPapi v5)

OddsPapi **v5** (`https://v5.oddspapi.io/...`) is **not authorized or verified** for MBM.

A `401 invalid_api_key` (or equivalent) from v5 is an **unsupported license boundary**,
not a normal runtime fallback. Production code must not call v5 hosts, must not use
v5 bookmaker/fixtures endpoints, and must not treat v5 as a recovery path.

Documented here for operators only. Remaining production-code occurrence count of
`v5` must stay **zero**.

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
| Byte-for-byte OddsPapi v4 responses | `source=oddspapi` | `intake/raw/oddspapi/` |

Never label synthetic JSON as OddsPapi recorded evidence.

## Market evidence rules

- Ingest **Pinnacle market prices** when returned under `bookmakerOdds.pinnacle`.
- OddsPapi supplies tournament, event, and market-line/price evidence.
- Player match logs and behavioral telemetry remain Mason-controlled or other specialized providers.
- **Do not** claim headshot (or other player-prop) availability unless demonstrated by a
  redacted authentic v4 response fixture.
- Failures become explicit PASS reasons via the source-attempt ledger (never generic
  “data unavailable”).
- Core publication remains blocked until authentic telemetry and evidence gates are satisfied.
