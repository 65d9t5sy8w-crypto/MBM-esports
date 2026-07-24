"""Pinned MBM Core artifact contract (shared; no adapter imports)."""

from __future__ import annotations

import hashlib
from pathlib import Path

EXPECTED_CORE_SHA256 = "d151b045fcfa9dd5225cd040740a5f246772bb14ceae5f10c16ff5b3fbf20151"
CORE_WHEEL_NAME = "mbm_core-0.1.0-py3-none-any.whl"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "vendor" / "mbm-core").is_dir():
            return parent
    return here.parents[1]


def core_wheel_path() -> Path:
    return repo_root() / "vendor" / "mbm-core" / CORE_WHEEL_NAME


def core_blocked_marker_path() -> Path:
    return repo_root() / "vendor" / "mbm-core" / "BLOCKED"


def core_wheel_present() -> bool:
    return core_wheel_path().is_file()


def core_wheel_sha256() -> str | None:
    path = core_wheel_path()
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_ready() -> bool:
    return core_wheel_sha256() == EXPECTED_CORE_SHA256


def core_status_message() -> str:
    if core_ready():
        return "Core READY (authentic v0.1.0 wheel verified)"
    return (
        "Core BLOCKED until the authentic v0.1.0 wheel is supplied "
        "(private GitHub Release Assets or successful v0.1.0 Release Actions artifact)"
    )
