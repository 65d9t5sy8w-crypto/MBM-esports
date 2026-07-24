# MBM Esports Data Intake Plan

## Decision

Do not use PandaScore or assume any paid provider. Build a provider-neutral intake layer that accepts verified API responses, exported game logs, manually supplied panels, and existing MBM fixtures.

Every record must carry:

- source;
- capture time;
- market scope;
- identity status;
- provenance;
- evidence completeness.

## Data Mason Can Supply

Accept JSON, CSV, API response bodies, or copied panels containing:

- fixture/event ID, teams, start time, and best-of format;
- confirmed rosters and player IDs;
- at least 10 recent player match logs where available;
- per-map kills, deaths, assists, headshots, opening kills/deaths, rounds played, side splits;
- map pool, veto, MR12 format, side bias;
- market board: player, stat, line, and scope;
- settled result after the match.

Never place secrets, cookies, session headers, or tokens in committed files.

## Canonical Evidence Envelope

Every provider/manual input must normalize into a canonical evidence envelope before reaching the projection layer:

```json
{
  "source": "provider-or-manual-drop",
  "captured_at": "ISO-8601",
  "fixture": {
    "event_id": "string",
    "team_a": "string",
    "team_b": "string",
    "start_time": "ISO-8601",
    "format": "bo3",
    "market_scope": "maps_1_2"
  },
  "players": [],
  "match_logs": [],
  "map_context": {},
  "market_lines": [],
  "evidence_status": "verified"
}
```

Store the raw input unchanged beside the normalized record. Raw evidence is immutable; normalized records are derived.

## Hard Rules

1. Resolve fixture, player identity, opponent, roster, and market scope before scoring.
2. Default CS2 player-prop scope is Maps 1–2.
3. Do not blend Map 1, Maps 1–2, and full-series samples without explicit scope conversion.
4. Preserve economy context: pistol, eco, anti-eco, force-buy, and full-buy events must not be blended blindly.
5. Keep provider-specific shapes inside adapters; universal MBM modules consume canonical types only.
6. If any critical input is unresolved, stale, or missing, return PASS with the exact reason.
7. Record every approved source attempted before returning unknown. Never return a generic “data unavailable.”

## Headshots Contract

A Headshots prop requires both gates:

- Opportunity Gate: projected Maps 1–2 kills support the line.
- Conversion Gate: adjusted headshot rate clears the required conversion rate.

Fail either gate or evidence completeness: PASS.
Recommendations are OVER, UNDER, or PASS only. No WATCHLIST.

## Required Modules

Create and test:

- `intake/raw/` — immutable raw payload handling;
- `intake/normalization/` — provider/manual payload translators;
- `intake/identity/` — player, team, and fixture resolution;
- `intake/evidence.py` — provenance, source-attempt ledger, staleness, explicit failure reasons;
- `fixtures/` — replayable CS2 panels and logs;
- `tests/` — unresolved identity, stale evidence, missing scope, and headshot-gate failures must result in PASS.

Unit tests must use recorded fixtures only. Live API requests are optional integration tests, never required for unit tests.

## Acceptance

An eligible live CS2 projection requires:

- resolved fixture, teams, player, roster, and market scope;
- complete feature provenance;
- valid distribution;
- Maps 1–2 opportunity and conversion evidence for Headshots;
- OVER, UNDER, or explicit PASS;
- no PandaScore dependency.
