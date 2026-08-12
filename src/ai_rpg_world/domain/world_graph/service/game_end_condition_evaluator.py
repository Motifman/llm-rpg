from __future__ import annotations

from typing import Any, FrozenSet, Mapping, Optional, Sequence

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    EntityPlacementPredicateContext,
    TickPredicateContext,
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    EntityAtSpotPredicate,
    FlagSetPredicate,
    TickAtLeastPredicate,
)


class GameEndConditionEvaluator:
    """スポットグラフ上のプレイヤー位置・フラグ・ティックに基づく終了判定（リポジトリ非依存）"""

    def __init__(
        self,
        predicate_evaluator: Optional[ScenarioPredicateEvaluator] = None,
    ) -> None:
        self._predicate_evaluator = predicate_evaluator or ScenarioPredicateEvaluator()

    @staticmethod
    def _evaluate_faction_elimination(
        condition: GameEndCondition,
        player_ids: Sequence[PlayerId],
        player_states: Optional[Mapping[int, Mapping[str, Any]]],
        player_outcomes: Optional[Mapping[int, PlayerOutcomeEnum]],
        result_on_match: Optional[GameResultEnum],
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
                result_on_match,
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
        # 成立したときに返す勝敗。**呼び出し側が決める。** 中立の ``end``
        # 配列だけは None を明示し、個人結果の混在を WIN / LOSE に畳まない。
        #
        # 以前は条件の型ごとに固定していた (陣営全滅なら LOSE、フラグ成立なら
        # WIN)。そのため win に書いた陣営条件が LOSE として返り、**インポスター
        # を追放したクルーが敗北扱い**になっていた。逆に lose に書いたフラグ
        # 条件は WIN になる。
        #
        # 型は「何が起きたか」しか表さない。それが勝ちか負けかは、シナリオが
        # どちらのリストに書いたかで決まる。既定値を置かないのは、新しい
        # 呼び出し側が黙ってどちらかに倒れるのを防ぐため。
        result_on_match: Optional[GameResultEnum],
    ) -> GameEndResult:
        t = condition.condition_type
        if t == GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST:
            declared = tuple(condition.required_flags or ())
            need = condition.min_set_count
            if not declared or need is None:
                # VO の __post_init__ が弾いているはずだが、直接組まれた
                # 条件が黙って未成立になると勝敗が永久に決まらない。
                raise GameEndConditionValidationException(
                    "FLAGS_SET_AT_LEAST に required_flags / min_set_count が"
                    "ありません"
                )
            # **宣言した作業だけを数える。** 立っているフラグ全体を数えると、
            # シナリオが別の用途で立てたフラグ (照明・救難信号) で勝ててしまう。
            done = sum(1 for name in declared if name in world_flags)
            if done >= need:
                return GameEndResult(
                    True,
                    result_on_match,
                    f"作業が {done}/{len(declared)} 完了 (必要 {need})",
                )
            return GameEndResult(
                False, None, f"作業は {done}/{len(declared)} (必要 {need})"
            )

        if t == GameEndConditionTypeEnum.FLAG_SET:
            name = condition.target_flag
            if not name:
                raise GameEndConditionValidationException(
                    "FLAG_SET に target_flag がありません"
                )
            result = self._predicate_evaluator.evaluate(
                FlagSetPredicate(name),
                WorldFlagPredicateContext(world_flags),
            )
            if ScenarioPredicateEvaluator.require_satisfaction(result):
                return GameEndResult(True, result_on_match, f"フラグ成立: {name}")
            return GameEndResult(False, None, "終了フラグ未成立")

        if t == GameEndConditionTypeEnum.TICK_LIMIT:
            limit = condition.tick_limit
            if limit is None or current_tick is None:
                raise GameEndConditionValidationException(
                    "TICK_LIMIT に current_tick または tick_limit がありません"
                )
            # loader/旧DTOはまだ非整数を拒否していない。入力厳格化は別PRで扱い、
            # この共通化では正規の整数値だけを型付き核へ移す。
            if isinstance(limit, int) and not isinstance(limit, bool):
                result = self._predicate_evaluator.evaluate(
                    TickAtLeastPredicate(limit),
                    TickPredicateContext(current_tick),
                )
                matched = ScenarioPredicateEvaluator.require_satisfaction(result)
            else:
                matched = current_tick.value >= limit
            if matched:
                return GameEndResult(True, result_on_match, f"ティック上限到達: {limit}")
            return GameEndResult(False, None, "ティック制限内")

        if t is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST:
            return self._evaluate_faction_elimination(
                condition, player_ids, player_states, player_outcomes,
                result_on_match,
            )

        if t is GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED:
            if player_outcomes is None:
                raise GameEndConditionValidationException(
                    "ALL_PLAYER_OUTCOMES_RESOLVED は player_outcomes を必要とします"
                )
            # 対象0人を空集合の論理で「全員確定」にすると、終了規則を持たない
            # 永続世界まで開始直後に終わりうる。実在する対象者を必須にする。
            if not player_ids:
                return GameEndResult(
                    False,
                    None,
                    "対象プレイヤーがいないため個人結果の確定待ち",
                )
            snapshot = {
                int(player_id): player_outcomes.get(
                    int(player_id), PlayerOutcomeEnum.UNRESOLVED
                )
                for player_id in player_ids
            }
            if all(outcome.is_resolved for outcome in snapshot.values()):
                return GameEndResult(
                    True,
                    result_on_match,
                    f"全 {len(snapshot)} プレイヤーの outcome が確定",
                    player_outcomes=snapshot,
                )
            return GameEndResult(
                False,
                None,
                "未確定プレイヤーあり",
                player_outcomes=snapshot,
            )

        if t in (GameEndConditionTypeEnum.ALL_AT_SPOT, GameEndConditionTypeEnum.ANY_AT_SPOT):
            spot = condition.target_spot_id
            if spot is None:
                raise GameEndConditionValidationException(
                    f"{t.value} に target_spot_id がありません"
                )
            placement_context = EntityPlacementPredicateContext(
                graph.entity_spot_mapping()
            )
            at_spot: list[bool] = []
            for pid in player_ids:
                eid = self.entity_id_for_player(pid)
                result = self._predicate_evaluator.evaluate(
                    EntityAtSpotPredicate(eid, spot),
                    placement_context,
                )
                at_spot.append(
                    ScenarioPredicateEvaluator.require_satisfaction(result)
                )
            if t == GameEndConditionTypeEnum.ALL_AT_SPOT:
                ok = len(at_spot) > 0 and all(at_spot)
                if ok:
                    return GameEndResult(True, result_on_match, f"全員がスポット {spot} にいます")
                return GameEndResult(False, None, "全員集合の条件未達")
            # ANY_AT_SPOT
            ok = any(at_spot)
            if ok:
                return GameEndResult(True, result_on_match, f"誰かがスポット {spot} にいます")
            return GameEndResult(False, None, "誰も対象スポットにいません")

        return GameEndResult(False, None, "未対応の終了条件です")
