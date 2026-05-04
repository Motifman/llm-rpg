"""WorldGraphEffectResult に載せるクロスドメイン効果の指示。

ドメイン間の疎結合を保つため、world_graph ドメインは combat/player ドメインの
型に直接依存しない。代わりに文字列ベースの spec を出力し、
application 層が PlayerStatusAggregate 等へ適用する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DamageSpec:
    damage: int
    message: str = ""


@dataclass(frozen=True)
class StatusEffectSpec:
    effect_type_name: str  # "POISON", "PARALYSIS" 等
    value: float
    duration_ticks: int


@dataclass(frozen=True)
class TeleportSpec:
    target_spot_id: int


@dataclass(frozen=True)
class AtmosphereUpdateSpec:
    spot_id: int
    lighting: Optional[str] = None
    temperature: Optional[str] = None
    hazard_level: Optional[int] = None
    hazard_description: Optional[str] = None
