"""Pydantic request-input models for Manual Mission Mode's mission-item
list — the discriminated-union counterpart to
services/manual_mission_builder.py's plain dataclasses. Shared between
server/api/missions.py (POST /mission/generate-manual) and
server/api/mission_library.py (POST /mission-library/manual), which both
build a mission from the same {home, items, speed_ms} shape — kept here
once rather than duplicated in both API modules.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from services.manual_mission_builder import (
    ChangeSpeedItemData,
    LandItemData,
    LoiterItemData,
    ManualItemData,
    RtlItemData,
    TakeoffItemData,
    WaypointItemData,
)


class TakeoffItemInput(BaseModel):
    type: Literal["takeoff"]
    lat: float
    lon: float
    altitude_m: float = Field(..., gt=0)


class WaypointItemInput(BaseModel):
    type: Literal["waypoint"]
    lat: float
    lon: float
    altitude_m: float = Field(..., gt=0)


class LoiterItemInput(BaseModel):
    type: Literal["loiter"]
    lat: float
    lon: float
    altitude_m: float = Field(..., gt=0)
    hold_time_s: float = Field(..., ge=0, le=600)


class RtlItemInput(BaseModel):
    type: Literal["rtl"]


class LandItemInput(BaseModel):
    type: Literal["land"]
    lat: float
    lon: float


class ChangeSpeedItemInput(BaseModel):
    type: Literal["change_speed"]
    speed_ms: float = Field(..., ge=0.5, le=25.0)


# Adding a new mission item type later means adding one *Input model above,
# one branch in to_builder_item() below, and one dataclass + one dispatch
# branch in manual_mission_builder.py — nothing else changes.
ManualItemInput = Annotated[
    Union[
        TakeoffItemInput,
        WaypointItemInput,
        LoiterItemInput,
        RtlItemInput,
        LandItemInput,
        ChangeSpeedItemInput,
    ],
    Field(discriminator="type"),
]


def to_builder_item(item: ManualItemInput) -> ManualItemData:
    """Map one validated request item to its manual_mission_builder dataclass."""
    if isinstance(item, TakeoffItemInput):
        return TakeoffItemData(latitude=item.lat, longitude=item.lon, altitude_m=item.altitude_m)
    if isinstance(item, WaypointItemInput):
        return WaypointItemData(latitude=item.lat, longitude=item.lon, altitude_m=item.altitude_m)
    if isinstance(item, LoiterItemInput):
        return LoiterItemData(
            latitude=item.lat, longitude=item.lon,
            altitude_m=item.altitude_m, hold_time_s=item.hold_time_s,
        )
    if isinstance(item, LandItemInput):
        return LandItemData(latitude=item.lat, longitude=item.lon)
    if isinstance(item, ChangeSpeedItemInput):
        return ChangeSpeedItemData(speed_ms=item.speed_ms)
    return RtlItemData()
