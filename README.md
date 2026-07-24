# MBM Esports (CS2)

Fixture-backed Counter-Strike 2 vertical slice for **Maps 1–2 Headshots**.

Target repository: `https://github.com/65d9t5sy8w-crypto/MBM-esports`

Contract: [`MBM_ESPORTS_DATA_INTAKE_PLAN.md`](MBM_ESPORTS_DATA_INTAKE_PLAN.md)

## Status

**Result: scaffold + intake complete / Core integration blocked**

This is **not** a finished Core-backed CS2 vertical slice. Intake and gate tests may
pass while Core-dependent acceptance tests are skipped; skips do **not** count toward
Core acceptance until the authentic wheel is present and its SHA-256 matches.

| Area | State |
|------|--------|
| Provider-neutral data intake (no PandaScore) | **Complete** |
| Headshots opportunity/conversion gates | **Complete** |
| Analyst dashboard (fixture/demo) | **Complete** |
| Esports scaffold (adapters, fixtures, CI) | **Complete** |
| MBM Core `v0.1.0` integration | **BLOCKED** |
| CS2 Core vertical-slice acceptance | **Not met** (pending Core) |

### Data intake (no paid provider)

Mason supplies verified API responses, exported logs, veto/map context, and market
panels. Everything normalizes to a canonical evidence envelope before scoring.
See the intake plan for the envelope schema and hard rules.

### Core dependency (blocked)

This slice requires the authentic, checksum-pinned MBM Core wheel:

- Artifact: `vendor/mbm-core/mbm_core-0.1.0-py3-none-any.whl`
- SHA-256: `d151b045fcfa9dd5225cd040740a5f246772bb14ceae5f10c16ff5b3fbf20151`
- Commit pin: `5d3c2e7892812858154061c199818ff91ab43f07`

**Do not rebuild or substitute Core.** Mason supplies the authentic wheel from
either the private GitHub Release **Assets** or the successful `v0.1.0`
**Release Actions** artifact—whichever actually contains it.

## Layout

```text
MBM_ESPORTS_DATA_INTAKE_PLAN.md
mbm/intake/                   # raw, normalization, identity, evidence
mbm/analyst/                   # canonical board assembly (no provider types in UI)
mbm/dashboard/                 # local HTML dashboard (stdlib HTTP)
mbm/behavioral/adapters/cs2/   # CS2-native types, headshots gates, projection
fixtures/cs2/                  # Replayable raw + normalized panels
tests/                         # Intake + gate + dashboard + Core-gate tests
vendor/mbm-core/               # Reserved for authentic wheel only
.github/workflows/ci.yml
```

## Recommendations

`OVER` / `UNDER` / `PASS` only. No `WATCHLIST`.

Headshots require both Maps 1–2 opportunity and conversion gates (or PASS with exact reason).

## Analyst dashboard (local)

Fixture/demo board for Mason — Today’s Board, Pick Detail, Settlement, Calibration.
No live API, database, Docker, or paid provider. Core status banner stays **BLOCKED**
until the authentic wheel is vendored; blocked/incomplete rows are never marked eligible.

```bash
python scripts/run_dashboard.py
# open http://127.0.0.1:8765/
```

## Local commands

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/report_status.py
python scripts/run_dashboard.py
python scripts/refresh_bo3gg.py --mode synthetic
python scripts/refresh_oddspapi.py --mode synthetic
# optional live smoke (honest UA only; stops on non-JSON/non-200):
# python scripts/refresh_bo3gg.py --mode live
# ODDSPAPI_API_KEY=... python scripts/refresh_oddspapi.py --mode live --sport cs2
git diff --check
git status --short
```

BO3 contract: [`docs/BO3GG_ENDPOINT_CONTRACT.md`](docs/BO3GG_ENDPOINT_CONTRACT.md).
OddsPapi **v4** contract: [`docs/ODDSPAPI_ENDPOINT_CONTRACT.md`](docs/ODDSPAPI_ENDPOINT_CONTRACT.md)
(`OddsPapiV4Adapter`; `/v4/sports`, `/v4/tournaments`, `/v4/odds-by-tournaments`;
sport IDs CS2=17, LoL=18, VALORANT=61). OddsPapi v5 is not authorized.
Synthetic unit fixtures live under `fixtures/bo3gg/synthetic/` and
`fixtures/oddspapi/synthetic/` and are **not** provider evidence.
Never commit OddsPapi API keys (`ODDSPAPI_API_KEY`).

## First live fixture — fields Mason must supply

- `event_id`, `team_a`, `team_b`, `start_time`, `format` (e.g. `bo3`)
- Confirmed rosters + player IDs (both sides)
- Target player + market board: `stat=headshots`, `line`, `scope=maps_1_2`
- ≥10 recent player match logs when available, each with Maps 1–2 kills/deaths/assists/headshots/opening kills-deaths/rounds/side splits + economy tags (`pistol|eco|anti_eco|force_buy|full_buy`)
- Map pool, veto, MR12, side bias
- `source`, `captured_at` (ISO-8601)
- Settled result after the match (replay grading)
- Never include secrets, cookies, session headers, or tokens
