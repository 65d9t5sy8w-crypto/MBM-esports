"""OddsPapi v4 provider adapter (HTTP + normalize). Provider shapes stay here."""

from mbm.providers.oddspapi.client import (
    API_KEY_ENV,
    BASE_URL,
    SPORT_ID_CS2,
    SPORT_ID_LOL,
    SPORT_ID_VALORANT,
    USER_AGENT,
    VERIFIED_ESPORTS_SPORT_IDS,
    OddsPapiHttpResult,
    OddsPapiV4Adapter,
    redact_api_key,
)
from mbm.providers.oddspapi.normalize import normalize_oddspapi_bundle
from mbm.providers.oddspapi.pipeline import refresh_from_synthetic, refresh_live_smoke

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "SPORT_ID_CS2",
    "SPORT_ID_LOL",
    "SPORT_ID_VALORANT",
    "USER_AGENT",
    "VERIFIED_ESPORTS_SPORT_IDS",
    "OddsPapiHttpResult",
    "OddsPapiV4Adapter",
    "normalize_oddspapi_bundle",
    "redact_api_key",
    "refresh_from_synthetic",
    "refresh_live_smoke",
]
