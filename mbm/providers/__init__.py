"""Provider adapters (HTTP + normalize). Provider shapes stay in subpackages."""

from mbm.providers.bo3gg.client import Bo3Client, Bo3HttpResult, USER_AGENT
from mbm.providers.bo3gg.normalize import normalize_bo3_bundle
from mbm.providers.bo3gg.pipeline import (
    refresh_from_synthetic as refresh_bo3_from_synthetic,
)
from mbm.providers.bo3gg.pipeline import refresh_live_smoke as refresh_bo3_live_smoke
from mbm.providers.oddspapi.client import (
    API_KEY_ENV as ODDSPAPI_API_KEY_ENV,
)
from mbm.providers.oddspapi.client import (
    CS2_SPORT_ID as ODDSPAPI_CS2_SPORT_ID,
)
from mbm.providers.oddspapi.client import OddsPapiClient, OddsPapiHttpResult
from mbm.providers.oddspapi.normalize import normalize_oddspapi_bundle
from mbm.providers.oddspapi.pipeline import (
    refresh_from_synthetic as refresh_oddspapi_from_synthetic,
)
from mbm.providers.oddspapi.pipeline import (
    refresh_live_smoke as refresh_oddspapi_live_smoke,
)

# Back-compat aliases for the original BO3-only export surface.
refresh_from_synthetic = refresh_bo3_from_synthetic
refresh_live_smoke = refresh_bo3_live_smoke

__all__ = [
    "Bo3Client",
    "Bo3HttpResult",
    "USER_AGENT",
    "normalize_bo3_bundle",
    "refresh_from_synthetic",
    "refresh_live_smoke",
    "refresh_bo3_from_synthetic",
    "refresh_bo3_live_smoke",
    "OddsPapiClient",
    "OddsPapiHttpResult",
    "ODDSPAPI_API_KEY_ENV",
    "ODDSPAPI_CS2_SPORT_ID",
    "normalize_oddspapi_bundle",
    "refresh_oddspapi_from_synthetic",
    "refresh_oddspapi_live_smoke",
]
