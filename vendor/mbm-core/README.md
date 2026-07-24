# MBM Core (blocked)

This directory is reserved for the **authentic** MBM Core `v0.1.0` wheel:

- File: `mbm_core-0.1.0-py3-none-any.whl`
- Expected SHA-256: `d151b045fcfa9dd5225cd040740a5f246772bb14ceae5f10c16ff5b3fbf20151`
- Upstream commit pin: `5d3c2e7892812858154061c199818ff91ab43f07`

## Status

**BLOCKED** — wheel not present in this workspace.

Do **not** rebuild, reconstruct, or substitute this artifact. Mason must supply the
verified `v0.1.0` wheel from an authenticated GitHub account—either the private
`mbm-core` Release **Assets** or the successful `v0.1.0` **Release Actions**
artifact, whichever actually contains it—before vendoring and before any
Core-dependent tests are claimed green.

## When the wheel arrives

1. Place `mbm_core-0.1.0-py3-none-any.whl` in this directory.
2. Verify SHA-256 matches the expected digest above.
3. Install from this path via `pyproject.toml`.
4. Re-run the CS2 vertical-slice tests.
