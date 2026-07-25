"""Reject sensitive keys before PrizePicks capture persistence."""

from __future__ import annotations

from typing import Any

from mbm.intake.types import SECRET_KEY_FRAGMENTS

# Extra fragments required by the PrizePicks bridge drop (reject, do not strip).
PRIZEPICKS_SENSITIVE_FRAGMENTS = SECRET_KEY_FRAGMENTS + (
    "device_id",
    "device-id",
    "deviceid",
    "cookie",
    "authorization",
)


class SensitivePayloadError(ValueError):
    """Raised when a capture payload contains forbidden credential material."""


def _walk_keys(payload: Any, *, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_s = str(key)
            key_l = key_s.lower()
            child = f"{path}.{key_s}" if path else key_s
            if any(frag in key_l for frag in PRIZEPICKS_SENSITIVE_FRAGMENTS):
                hits.append(child)
            hits.extend(_walk_keys(value, path=child))
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            hits.extend(_walk_keys(item, path=f"{path}[{i}]"))
    return hits


def reject_sensitive_payload(payload: Any) -> None:
    """Raise if cookies, tokens, auth headers, device IDs, or secrets are present."""
    hits = _walk_keys(payload)
    if hits:
        raise SensitivePayloadError(
            "PrizePicks capture rejected: sensitive keys present: " + ", ".join(hits[:12])
        )
