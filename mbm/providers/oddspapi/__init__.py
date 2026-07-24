"""OddsPapi provider adapter (HTTP + normalize). Provider shapes stay here."""

from mbm.providers.oddspapi.client import (
    API_KEY_ENV,
    BASE_URL,
    CS2_SPORT_ID,
    OddsPapiClient,
    OddsPapiHttpResult,
    USER_AGENT,
    redact_api_key,
)
from mbm.providers.oddspapi.normalize import normalize_oddspapi_bundle
from mbm.providers.oddspapi.pipeline import refresh_from_synthetic, refresh_live_smoke

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "CS2_SPORT_ID",
    "OddsPapiClient",
    "OddsPapiHttpResult",
    "USER_AGENT",
    "normalize_oddspapi_bundle",
    "redact_api_key",
    "refresh_from_synthetic",
    "refresh_live_smoke",
]
