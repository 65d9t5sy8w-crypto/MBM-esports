# MBM — PrizePicks Browser Endpoint Intake

## Objective

Connect the live PrizePicks board to the existing universal capture endpoint without
touching scoring, pick generation, CS2 routes, rate-limit handling, or shared error
helpers.

```text
PrizePicks browser response
  -> browser bridge
  -> POST /api/live/prizepicks/capture-board
  -> raw append-only snapshot + normalized records
  -> existing sport-specific live-board readers
```

## Locked constraints

* Do not fetch or replay authentication material from MBM.
* Do not bypass DataDome or attempt server-side impersonation.
* Do not create picks, scores, auto-passes, or confidence changes.
* Do not silently delete absent props. Mark removals only on an explicit, successful
  `authoritative_capture=true` capture.
* Default `authoritative_capture` to `false`.
* Reject payloads containing cookies, authorization headers, tokens, device IDs, or
  other sensitive keys before persistence.
* Preserve source selection: `provider valid -> browser bridge -> last-known-good -> none`.

## Existing MBM endpoints — do not rename

```text
POST /api/live/prizepicks/capture-board
GET  /api/live/prizepicks/board-snapshots/latest
GET  /api/live/prizepicks/board-history
GET  /api/live/prizepicks/health
```

## Browser endpoint

Use the PrizePicks response returned in the authenticated browser session. Capture only
response JSON—never request headers, cookies, or browser-storage values.

```text
GET https://api.prizepicks.com/projections
```

## Browser bridge request contract

```json
{
  "source": "prizepicks_browser_bridge",
  "captured_at": "2026-07-24T00:00:00Z",
  "sports": ["cs2", "valorant", "cod", "lol", "dota", "mlb", "nfl"],
  "authoritative_capture": false,
  "payload": {
    "data": [],
    "included": []
  }
}
```

1. `payload` is the unmodified PrizePicks JSON response body.
2. `sports` is optional; omit it for the full returned board.
3. Filter after capture. A scoped capture must never remove another sport’s props.
4. Invalid or empty browser responses must not call MBM.
5. Non-authoritative capture updates the latest snapshot but never clears active props.

## Required bridge behavior

1. Intercept or explicitly fetch the browser-visible projections response.
2. Validate the parsed body has a `data` array.
3. Preserve raw response fields inside `payload`.
4. Reject sensitive keys before sending.
5. POST JSON using the established bridge token/header only.
6. Show capture timestamp, record count, and status.
7. Show `CAPTURED` separately from `CLEARED`.

## Acceptance checks

```text
- One successful browser response creates one append-only raw snapshot.
- The existing adapter produces normalized records.
- Unresolved player identity stays unverified; never merge by name alone.
- authoritative_capture=false never marks a prop REMOVED.
- A scoped CS2 capture cannot remove VALORANT/COD/LoL/Dota props.
- Health returns only its eight allowlisted fields—no props or credentials.
- Every PrizePicks route returns scoring_touched: false.
```

## Do not change

```text
/api/live/cs2
scoring modules
verdict tallying
429 handling
shared error helpers
universal PrizePicks capture semantics
```
