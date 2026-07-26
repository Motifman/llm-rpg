from __future__ import annotations

from typing import Any, FrozenSet, Mapping, Optional, Sequence

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult


class GameEndConditionEvaluator:
    """スポットグラフ上のプレイヤー位置・フラグ・ティックに基づく終了判定（リポジトリ非依存）"""

    @staticmethod
    def _evaluate_faction_elimination(
        condition: GameEndCondition,
        player_ids: Sequence[PlayerId],
        player_states: Optional[Mapping[int, Mapping[str, Any]]],
        player_outcomes: Optional[Mapping[int, PlayerOutcomeEnum]],
    ) -> GameEndResult:
        """``required_state`` を満たす生存者が閾値以下かを判定する。

        生存から外れるのは ``PlayerOutcomeEnum.DEAD`` が確定した相手だけ。
        倒れている (``is_down``) だけの相手は蘇生できるので生存として数える。
        """
        required_state = condition.required_state
        max_surviving = condition.max_surviving
        if not required_state or max_surviving is None:
            raise GameEndConditionValidationException(
                "SURVIVING_PLAYERS_WITH_STATE_AT_MOST に required_state / "
                "max_surviving がありません"
            )
        if player_states is None or player_outcomes is None:
            raise GameEndConditionValidationException(
                "SURVIVING_PLAYERS_WITH_STATE_AT_MOST は player_states と "
                "player_outcomes を必要とします (未配線だと勝敗が永久に"
                "成立しません)"
            )

        surviving = 0
        for pid in player_ids:
            key = int(pid)
            state = player_states.get(key) or {}
            if any(state.get(k) != v for k, v in required_state.items()):
                continue
            outcome = player_outcomes.get(key)
            if outcome is not None and outcome.is_eliminated:
                continue
            surviving += 1

        described = ", ".join(f"{k}={v}" for k, v in required_state.items())
        if surviving <= int(max_surviving):
            return GameEndResult(
                True,
                GameResultEnum.LOSE,
                f"陣営の生存者が尽きた ({described}: 残り{surviving}人)",
            )
        return GameEndResult(
            False, None, f"陣営はまだ生存している ({described}: 残り{surviving}人)"
        )

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
        *,
        # 陣営条件 (SURVIVING_PLAYERS_WITH_STATE_AT_MOST) の判定材料。
        # player_id (int) -> PlayerStatusAggregate.state / 確定 outcome。
        # 該当条件で渡っていなければ黙って未成立にせず例外にする
        # (勝敗が永久に成立しないまま実験が走り続けるのを避ける)。
        player_states: Optional[Mapping[int, Mapping[str, Any]]] = None,
        player_outcomes: Optional[Mapping[int, PlayerOutcomeEnum]] = None,
    ) -> GameEndResult:
        t = condition.condition_type
        if t == GameEndConditionTypeEnum.FLAG_SET:
            name = condition.target_flag
            if not name:
                raise GameEndConditionValidationException(
                    "FLAG_SET に target_flag がありません"
                )
            if name in world_flags:
                return GameEndResult(True, GameResultEnum.WIN, f"フラグ成立: {name}")
            return GameEndResult(False, None, "終了フラグ未成立")

        if t == GameEndConditionTypeEnum.TICK_LIMIT:
            limit = condition.tick_limit
            if limit is None or current_tick is None:
                raise GameEndConditionValidationException(
                    "TICK_LIMIT に current_tick または tick_limit がありません"
                )
            if current_tick.value >= limit:
                return GameEndResult(True, GameResultEnum.LOSE, f"ティック上限到達: {limit}")
            return GameEndResult(False, None, "ティック制限内")

        if t is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST:
            return self._evaluate_faction_elimination(
                condition, player_ids, player_states, player_outcomes
            )

        if t in (GameEndConditionTypeEnum.ALL_AT_SPOT, GameEndConditionTypeEnum.ANY_AT_SPOT):
            spot = condition.target_spot_id
            if spot is None:
                raise GameEndConditionValidationException(
                    f"{t.value} に target_spot_id がありません"
                )
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
