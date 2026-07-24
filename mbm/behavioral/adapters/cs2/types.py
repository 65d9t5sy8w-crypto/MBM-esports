"""CS2-native types (remain inside this adapter package)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CS2MarketKey(str, Enum):
    MAPS_1_2_HEADSHOTS = "cs2.maps_1_2.headshots"


@dataclass(frozen=True)
class CS2MapWindow:
    """Inclusive map window for aggregate markets (e.g. maps 1–2)."""

    start_map: int
    end_map: int

    def __post_init__(self) -> None:
        if self.start_map < 1 or self.end_map < self.start_map:
            raise ValueError(f"invalid map window: {self.start_map}-{self.end_map}")


@dataclass(frozen=True)
class CS2HeadshotsPanel:
    """Fixture-backed panel for Maps 1–2 headshots projection."""

    match_id: str
    market: CS2MarketKey
    map_window: CS2MapWindow
    line: float
    features: dict[str, Any]
    approved_for_publication: bool

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CS2HeadshotsPanel:
        window = payload["map_window"]
        return cls(
            match_id=str(payload["match_id"]),
            market=CS2MarketKey(payload["market"]),
            map_window=CS2MapWindow(
                start_map=int(window["start_map"]),
                end_map=int(window["end_map"]),
            ),
            line=float(payload["line"]),
            features=dict(payload["features"]),
            approved_for_publication=bool(payload["approved_for_publication"]),
        )
