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
    SPORT_ID_CS2,
    SPORT_ID_LOL,
    SPORT_ID_VALORANT,
    VERIFIED_ESPORTS_SPORT_IDS,
    OddsPapiHttpResult,
    OddsPapiV4Adapter,
)
from mbm.providers.oddspapi.normalize import normalize_oddspapi_bundle
from mbm.providers.oddspapi.pipeline import (
    refresh_from_synthetic as refresh_oddspapi_from_synthetic,
)
from mbm.providers.oddspapi.pipeline import (
    refresh_live_smoke as refresh_oddspapi_live_smoke,
)
from mbm.providers.balldontlie.client import (
    API_KEY_ENV as BALLDONTLIE_API_KEY_ENV,
)
from mbm.providers.balldontlie.client import (
    BallDontLieHttpResult,
    BallDontLieNbaAdapter,
)
from mbm.providers.balldontlie.normalize import normalize_balldontlie_bundle
from mbm.providers.balldontlie.pipeline import (
    refresh_from_synthetic as refresh_balldontlie_from_synthetic,
)
from mbm.providers.balldontlie.pipeline import (
    refresh_live_smoke as refresh_balldontlie_live_smoke,
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
    "OddsPapiV4Adapter",
    "OddsPapiHttpResult",
    "ODDSPAPI_API_KEY_ENV",
    "SPORT_ID_CS2",
    "SPORT_ID_LOL",
    "SPORT_ID_VALORANT",
    "VERIFIED_ESPORTS_SPORT_IDS",
    "normalize_oddspapi_bundle",
    "refresh_oddspapi_from_synthetic",
    "refresh_oddspapi_live_smoke",
    "BallDontLieNbaAdapter",
    "BallDontLieHttpResult",
    "BALLDONTLIE_API_KEY_ENV",
    "normalize_balldontlie_bundle",
    "refresh_balldontlie_from_synthetic",
    "refresh_balldontlie_live_smoke",
]
