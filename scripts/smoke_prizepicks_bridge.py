#!/usr/bin/env python3
"""Non-authoritative PrizePicks bridge smoke: live HTTP capture, scoring untouched.

Simulates the browser bridge POST (response JSON + bridge token only — no cookies).
Uses the synthetic board fixture as the projections body (not recorded PP evidence).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.live.prizepicks_http import (  # noqa: E402
    BRIDGE_TOKEN_HEADER,
    PATH_CAPTURE,
    PATH_HEALTH,
    serve_prizepicks,
)
from mbm.providers.prizepicks.service import PrizePicksCaptureService  # noqa: E402

FIX_OK = ROOT / "fixtures" / "prizepicks" / "synthetic" / "board_ok.json"
SMOKE_TOKEN = "mbm-smoke-bridge-token"


def _projections_payload(path: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    body.pop("_fixture_meta", None)
    if not isinstance(body.get("data"), list) or not body["data"]:
        raise SystemExit("smoke aborted: fixture missing non-empty data[] (bridge would not call MBM)")
    return body


def _bridge_body(payload: dict) -> dict:
    """Mirror browser bridge request: JSON only, authoritative_capture=false."""
    return {
        "source": "prizepicks_browser_bridge",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authoritative_capture": False,
        "payload": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PrizePicks browser-bridge capture smoke")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIX_OK,
        help="Projections-shaped JSON (default: synthetic board_ok)",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Existing capture-board URL (if empty, start ephemeral local server)",
    )
    parser.add_argument("--token", default=SMOKE_TOKEN)
    args = parser.parse_args()

    payload = _projections_payload(args.fixture)
    bridge = _bridge_body(payload)
    raw = json.dumps(bridge).encode("utf-8")

    server = None
    data_dir = None
    capture_url = args.url

    if not capture_url:
        data_dir = tempfile.TemporaryDirectory(prefix="mbm-pp-smoke-")
        service = PrizePicksCaptureService(Path(data_dir.name), bridge_token=args.token)
        server = serve_prizepicks(service, host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        capture_url = f"http://127.0.0.1:{port}{PATH_CAPTURE}"
        health_url = f"http://127.0.0.1:{port}{PATH_HEALTH}"
    else:
        health_url = capture_url.replace(PATH_CAPTURE, PATH_HEALTH)

    headers = {
        "Content-Type": "application/json",
        BRIDGE_TOKEN_HEADER: args.token,
        # Intentionally no Cookie / Authorization — bridge contract.
    }

    try:
        req = urllib.request.Request(
            capture_url,
            data=raw,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        print("MBM PrizePicks bridge smoke")
        print(f"  url:                  {capture_url}")
        print(f"  captured_at:          {result.get('captured_at')}")
        print(f"  record_count:         {result.get('record_count')}")
        print(f"  status:               {result.get('status')}")
        print(f"  cleared_status:       {result.get('cleared_status')}")
        print(f"  authoritative_capture:{result.get('authoritative_capture')}")
        print(f"  scoring_touched:      {result.get('scoring_touched')}")
        print(f"  snapshot_id:          {result.get('snapshot_id')}")

        assert result.get("status") == "CAPTURED", result
        assert result.get("cleared_status") == "NOT_CLEARED", result
        assert result.get("authoritative_capture") is False, result
        assert result.get("scoring_touched") is False, result
        assert int(result.get("record_count") or 0) >= 1, result

        # Health still eight fields / scoring untouched.
        hreq = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(hreq, timeout=10) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        assert health.get("scoring_touched") is False, health
        assert len(health) == 8, health

        print("SMOKE OK: non-authoritative live capture via bridge contract")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"SMOKE FAIL: HTTP {exc.code} {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if data_dir is not None:
            data_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
