# MBM PrizePicks browser bridge

Posts **response JSON only** from the authenticated PrizePicks browser session into:

`POST /api/live/prizepicks/capture-board`

## Hard rules

- No cookies, request headers, browser storage, or auth material may be forwarded to MBM.
- Only `Content-Type: application/json` and optional `X-MBM-Bridge-Token` go to MBM.
- Ordinary `fetch` with `credentials: "omit"` on the MBM POST.
- Userscript metadata: `@grant none` — **no** `@connect` (not `127.0.0.1`, not `localhost`, not `*`).
- Invalid / non-JSON / empty `data` arrays **do not** call MBM.
- Default `authoritative_capture: false` (never clears props from the bridge).

## Local dashboard vs live capture

- Local dashboard may run at `http://127.0.0.1:8765` for **inspection only**.
- Live PrizePicks capture must target:

```text
https://<MBM-domain>/api/live/prizepicks/capture-board
```

Do **not** set or document `127.0.0.1` as a live capture destination.

```js
localStorage.setItem(
  "mbm_prizepicks_capture_url",
  "https://<MBM-domain>/api/live/prizepicks/capture-board"
);
localStorage.setItem("mbm_bridge_token", "<token>");
```

## Install (live)

1. Deploy / expose the capture API behind HTTPS (same locked paths; CORS for the PrizePicks origin).
2. Install a userscript manager and add [`prizepicks_bridge.user.js`](prizepicks_bridge.user.js).
3. On the PrizePicks origin, set `localStorage` as above (HTTPS URL required).

## Behavior

1. Intercepts `fetch` to `https://api.prizepicks.com/projections`.
2. Validates `payload.data` is a non-empty array.
3. Rejects sensitive keys client-side before POST.
4. Shows `captured_at`, `record_count`, `status` (`CAPTURED`), and `cleared_status` separately.
5. Manual refetch: **Alt+Shift+M**.

## Smoke (local HTTP path only — not live browser)

```bash
python scripts/smoke_prizepicks_bridge.py
```

Ephemeral local HTTP smoke of the bridge contract using the synthetic fixture. This does **not** replace the HTTPS live bridge and is not a live capture destination for the userscript.
