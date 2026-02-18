"""
モンスターの「次の一手」（移動先・スキルスロット）を解決するポート。
Monster ドメインはこのインターフェースにのみ依存し、マップ・パス探索・スキル選択の実装は
アプリケーション層が注入する（PhysicalMapAggregate, PathfindingService, SkillSelectionPolicy 等）。
"""

from typing import Protocol, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
    from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
    from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction


class IMonsterActionResolver(Protocol):
    """
    モンスターの現在状態と観測から、実行すべき BehaviorAction（MOVE 座標 or USE_SKILL slot）を返す。
    実装はアプリケーション層にあり、PhysicalMapAggregate と PathfindingService 等を使って解決する。
    """

    def resolve_action(
        self,
        monster: "MonsterAggregate",
        observation: "BehaviorObservation",
        actor_coordinate: Coordinate,
    ) -> "BehaviorAction":
        """
        次の一手を決定する。

        Args:
            monster: モンスター集約（行動状態を参照する）
            observation: 現在の観測
            actor_coordinate: アクターの現在座標

        Returns:
            実行すべき BehaviorAction（MOVE / USE_SKILL / WAIT）
        """
        ...
