"""モンスターの行動遷移を集約へ渡す値。タイルの観測からの計算は退役済み。"""

from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class SpotTargetParams:
    """spot_target を適用する際のパラメータ。"""
    target_id: WorldObjectId
    coordinate: Coordinate
    effective_flee_threshold: float | None = None
    allow_chase: bool | None = None


@dataclass
class StateTransitionResult:
    """
    状態遷移の適用内容。モンスター集約がこの値を適用し、イベントを発行する。
    """
    apply_enrage: bool = False
    flee_from_threat_id: WorldObjectId | None = None
    flee_from_threat_coordinate: Coordinate | None = None
    spot_target_params: SpotTargetParams | None = None
    do_lose_target: bool = False
    lost_target_id: WorldObjectId | None = None
    last_known_coordinate: Coordinate | None = None
