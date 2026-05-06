"""WorldGraphEffectResult に載せるクロスドメイン効果の指示。

ドメイン間の疎結合を保つため、world_graph ドメインは combat/player ドメインの
型に直接依存しない。代わりに文字列ベースの spec を出力し、
application 層が PlayerStatusAggregate 等へ適用する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ai_rpg_world.domain.world_graph.value_object.passage import Passage


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


@dataclass(frozen=True)
class CreateConnectionSpec:
    from_spot_id: int
    to_spot_id: int
    connection_name: str
    description: str = ""
    travel_ticks: int = 1
    is_bidirectional: bool = False
    passage: Passage = field(default_factory=Passage.open)


@dataclass(frozen=True)
class DestroyConnectionSpec:
    connection_id: int


@dataclass(frozen=True)
class SatisfyNeedSpec:
    need_type_name: str  # "HUNGER", "FATIGUE" 等
    amount: int


@dataclass(frozen=True)
class PassageStateUpdateSpec:
    """接続の Passage を新しい状態へ遷移させる指示。

    application 層が `SpotGraphAggregate.set_connection_passage_state` を
    呼び出して反映する。`traversable_override` / `sound_permeability_override`
    を指定すると、kind+new_state の既定値を上書きできる。
    """

    connection_id: int
    new_state: str  # 対象接続の passage.kind に対応する状態文字列
    traversable_override: Optional[bool] = None
    sound_permeability_override: Optional[float] = None
