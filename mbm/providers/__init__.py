"""BO3.gg provider adapter (HTTP + normalize). Provider shapes stay here."""

from mbm.providers.bo3gg.client import Bo3Client, Bo3HttpResult, USER_AGENT
from mbm.providers.bo3gg.normalize import normalize_bo3_bundle
from mbm.providers.bo3gg.pipeline import refresh_from_synthetic, refresh_live_smoke

__all__ = [
    "Bo3Client",
    "Bo3HttpResult",
    "USER_AGENT",
    "normalize_bo3_bundle",
    "refresh_from_synthetic",
    "refresh_live_smoke",
]
