"""CS2 adapter surface.

CS2-native types stay in this package. Core integration is blocked until the
authentic mbm-core v0.1.0 wheel is vendored.
"""

from mbm.behavioral.adapters.cs2.headshots import HeadshotsDecision, evaluate_headshots
from mbm.behavioral.adapters.cs2.types import (
    CS2HeadshotsPanel,
    CS2MapWindow,
    CS2MarketKey,
)
from mbm.behavioral.adapters.cs2.projection import (
    project_headshots_from_envelope,
    project_maps_1_2_headshots,
)

__all__ = [
    "CS2HeadshotsPanel",
    "CS2MapWindow",
    "CS2MarketKey",
    "HeadshotsDecision",
    "evaluate_headshots",
    "project_headshots_from_envelope",
    "project_maps_1_2_headshots",
]
