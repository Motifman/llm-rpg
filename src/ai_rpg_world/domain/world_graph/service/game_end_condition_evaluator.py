from __future__ import annotations

from typing import FrozenSet, Optional, Sequence

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import EntityNotInGraphException
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult


class GameEndConditionEvaluator:
    """スポットグラフ上のプレイヤー位置・フラグ・ティックに基づく終了判定（リポジトリ非依存）"""

    @staticmethod
    def entity_id_for_player(player_id: PlayerId) -> EntityId:
        return EntityId.create(int(player_id))

    def evaluate(
        self,
        graph: SpotGraphAggregate,
        condition: GameEndCondition,
        world_flags: FrozenSet[str],
        player_ids: Sequence[PlayerId],
        current_tick: Optional[WorldTick] = None,
    ) -> GameEndResult:
        t = condition.condition_type
        if t == GameEndConditionTypeEnum.FLAG_SET:
            name = condition.target_flag
            if not name:
                return GameEndResult(False, None, "FLAG_SET に target_flag がありません")
            if name in world_flags:
                return GameEndResult(True, GameResultEnum.WIN, f"フラグ成立: {name}")
            return GameEndResult(False, None, "終了フラグ未成立")

        if t == GameEndConditionTypeEnum.TICK_LIMIT:
            limit = condition.tick_limit
            if limit is None or current_tick is None:
                return GameEndResult(False, None, "TICK_LIMIT に tick または tick_limit がありません")
            if current_tick.value >= limit:
                return GameEndResult(True, GameResultEnum.LOSE, f"ティック上限到達: {limit}")
            return GameEndResult(False, None, "ティック制限内")

        if t in (GameEndConditionTypeEnum.ALL_AT_SPOT, GameEndConditionTypeEnum.ANY_AT_SPOT):
            spot = condition.target_spot_id
            if spot is None:
                return GameEndResult(False, None, "スポット条件に target_spot_id がありません")
            at_spot: list[bool] = []
            for pid in player_ids:
                eid = self.entity_id_for_player(pid)
                try:
                    s = graph.get_entity_spot(eid)
                except EntityNotInGraphException:
                    at_spot.append(False)
                    continue
                at_spot.append(s == spot)
            if t == GameEndConditionTypeEnum.ALL_AT_SPOT:
                ok = len(at_spot) > 0 and all(at_spot)
                if ok:
                    return GameEndResult(True, GameResultEnum.WIN, f"全員がスポット {spot} にいます")
                return GameEndResult(False, None, "全員集合の条件未達")
            # ANY_AT_SPOT
            ok = any(at_spot)
            if ok:
                return GameEndResult(True, GameResultEnum.WIN, f"誰かがスポット {spot} にいます")
            return GameEndResult(False, None, "誰も対象スポットにいません")

        return GameEndResult(False, None, "未対応の終了条件です")
