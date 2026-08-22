"""ScenarioEventCondition の評価器。

scenario_event の発火条件と reactive binding の predicate の両方で
共有される評価ロジックを 1 箇所に集約する。leaf 条件の各タイプと
合成条件 (NOT/AND/OR) を再帰評価する。
"""

from __future__ import annotations

import logging
import random
from typing import Callable, Iterable, Optional

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_graph.scenario_predicate_evaluation import (
    ProbabilityDecision,
    ScenarioPredicateEvaluation,
)
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    EntityPlacementPredicateContext,
    OwnedItemSpecsPredicateContext,
    StateValuesPredicateContext,
    TickPredicateContext,
    WeatherTypePredicateContext,
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    EntityAtSpotPredicate,
    EntityCountAtSpotAtLeastPredicate,
    FlagSetPredicate,
    ItemSpecOwnedPredicate,
    StateIntAtLeastPredicate,
    StateValuesMatchPredicate,
    TickAtLeastPredicate,
    WeatherTypeIsPredicate,
)


_logger = logging.getLogger(__name__)
from ai_rpg_world.application.world_graph.spot_object_lookup import find_object_in_graph
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.service.players_at_spot_condition import (
    DEFAULT_REQUIRED_PLAYER_COUNT,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
    PredicateResult,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


#: この評価器が実際に判定できる条件の種類。
#:
#: **読み込み時の照合に使う。** これが無かったとき、綴りを間違えた条件は
#: 黙って読み込みを通り、``_evaluate`` の末尾で False に落ちていた。
#:
#:     {"condition_type": "TICK_AT_LEATS", "value": 3}
#:     → 読み込みが通り、この出来事は永久に発火しない
#:
#: 誰も気づけない。妨害のように条件を大量に書く機能では、1 文字の違いが
#: 「なぜか何も起きない」になる。
#:
#: **分岐を足したらここにも足すこと。** 足し忘れは網羅テストが落とす
#: (モジュールの本文から ``ctype == "..."`` を拾って突き合わせている)。
KNOWN_CONDITION_TYPES: frozenset = frozenset({
    # 合成
    "NOT", "AND", "OR",
    # 時刻
    "TICK_AT_LEAST", "TICK_BETWEEN", "TICK_MODULO",
    # 世界フラグ
    "FLAG_SET", "FLAG_NOT_SET",
    # 位置・所持・世界フェーズ
    "PLAYER_AT_SPOT", "PLAYERS_AT_SPOT", "HAS_ITEM", "GAME_PHASE_IS",
    # オブジェクトの状態
    "OBJECT_STATE", "OBJECT_STATE_TICK_AT_LEAST", "OBJECT_STATE_INT_AT_LEAST",
    "OBJECT_STATE_INT_GREATER_THAN_OTHER",
    # 環境
    "WEATHER_IS",
    # 確率
    "PROBABILITY",
})


class ScenarioConditionEvaluator:
    """ScenarioEventCondition を current_tick / graph / repos の文脈で評価する。

    repository 等の世界状態は変更しないが、PROBABILITY 用の乱数位置は進む。
    用途間の既存の消費順を保つため、scenario_event_stage と
    reactive_binding_stage は 1 つのインスタンスと乱数源を共有する。
    """

    def __init__(
        self,
        *,
        world_flag_state: MutableWorldFlagState,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        weather_state_provider: Optional[Callable[[], WeatherState]] = None,
        game_phase_provider: Optional[Callable[[], GamePhase]] = None,
        random_source: Optional[random.Random] = None,
        predicate_evaluator: Optional[ScenarioPredicateEvaluator] = None,
    ) -> None:
        self._world_flag_state = world_flag_state
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        # WEATHER_IS 条件の評価に必要。None の場合 WEATHER_IS は常に False。
        # provider が返すのは WeatherState 互換オブジェクト
        # (.weather_type.value で天候名が取れる構造)。
        self._weather_state_provider = weather_state_provider
        # GAME_PHASE_IS は production で唯一の GamePhaseStore から読む。
        # 条件を使うのに未配線なら False へ縮退させず、構成ミスとして止める。
        self._game_phase_provider = game_phase_provider
        # Phase D-1: PROBABILITY 評価用 RNG。未注入なら新しい random.Random()
        # で初期化するので非決定的。テストや再現実験では seed 注入で固定化する。
        self._random = random_source or random.Random()
        self._predicate_evaluator = predicate_evaluator or ScenarioPredicateEvaluator()

    def validate_dependencies(
        self, conditions: Iterable[ScenarioEventCondition]
    ) -> None:
        """宣言された条件に必要な provider が構築時点で揃っているか確かめる。

        評価時まで待つと、長走実験の途中で初めて該当条件へ到達した時点まで
        配線漏れが潜伏する。条件を受け取る各 stage の constructor から呼び、
        world を動かす前に失敗させる。
        """
        if self._game_phase_provider is not None:
            return

        def uses_game_phase(condition: ScenarioEventCondition) -> bool:
            return condition.condition_type == "GAME_PHASE_IS" or any(
                uses_game_phase(child) for child in condition.children
            )

        if any(uses_game_phase(condition) for condition in conditions):
            raise RuntimeError(
                "GAME_PHASE_IS requires game_phase_provider wiring"
            )

    def evaluate(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        """1 つの条件（leaf or 合成）を再帰的に評価する。"""
        self.validate_dependencies((cond,))
        return self._as_legacy_bool(
            self.evaluate_result(cond, current_tick, graph)
        )

    def evaluate_result(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> PredicateResult[ScenarioEventCondition]:
        """1条件の成立可否と、未成立の理由・場所を返す。"""
        return self.evaluate_diagnostic(cond, current_tick, graph).result

    def evaluate_diagnostic(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> ScenarioPredicateEvaluation:
        """1条件を一度だけ評価し、実際に消費した確率判断も返す。"""
        decisions: list[ProbabilityDecision] = []
        result = self._evaluate(
            cond,
            current_tick,
            graph,
            target_player_id=None,
            current_path=(),
            probability_decisions=decisions,
        )
        return ScenarioPredicateEvaluation(result, tuple(decisions))

    def evaluate_for_player(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> bool:
        """対象プレイヤーの文脈で 1 条件を評価する。

        ``PLAYER_AT_SPOT`` や ``HAS_ITEM`` を世界全体ではなく指定した本人へ
        絞る。対象を渡し忘れたときに従来の世界条件へ縮退しないよう、入口で
        ``PlayerId`` を必須にする。
        """
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        self.validate_dependencies((cond,))
        return self._as_legacy_bool(
            self.evaluate_result_for_player(
                cond,
                current_tick,
                graph,
                target_player_id=target_player_id,
            )
        )

    def evaluate_result_for_player(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> PredicateResult[ScenarioEventCondition]:
        """対象プレイヤーの文脈で1条件の構造化結果を返す。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        return self.evaluate_diagnostic_for_player(
            cond,
            current_tick,
            graph,
            target_player_id=target_player_id,
        ).result

    def evaluate_diagnostic_for_player(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> ScenarioPredicateEvaluation:
        """対象者文脈で一度だけ評価し、確率判断も返す。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        decisions: list[ProbabilityDecision] = []
        result = self._evaluate(
            cond,
            current_tick,
            graph,
            target_player_id,
            current_path=(),
            probability_decisions=decisions,
        )
        return ScenarioPredicateEvaluation(result, tuple(decisions))

    def evaluate_all(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        """複数条件の暗黙 AND（全部真なら真）。"""
        self.validate_dependencies(conditions)
        return self._as_legacy_bool(
            self.evaluate_all_result(conditions, current_tick, graph)
        )

    def evaluate_all_result(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> PredicateResult[ScenarioEventCondition]:
        """複数条件を暗黙ANDとして評価し、最初の失敗経路を返す。"""
        return self.evaluate_all_diagnostic(conditions, current_tick, graph).result

    def evaluate_all_diagnostic(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> ScenarioPredicateEvaluation:
        """暗黙ANDを一度だけ評価し、実際に消費した確率判断も返す。"""
        decisions: list[ProbabilityDecision] = []
        result = self._evaluate_all(
            conditions,
            current_tick,
            graph,
            target_player_id=None,
            current_path=(),
            probability_decisions=decisions,
        )
        return ScenarioPredicateEvaluation(result, tuple(decisions))

    def evaluate_all_for_player(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> bool:
        """対象プレイヤーの文脈で複数条件を暗黙の AND として評価する。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        self.validate_dependencies(conditions)
        return self._as_legacy_bool(
            self.evaluate_all_result_for_player(
                conditions,
                current_tick,
                graph,
                target_player_id=target_player_id,
            )
        )

    def evaluate_all_result_for_player(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> PredicateResult[ScenarioEventCondition]:
        """対象者文脈の暗黙ANDを評価し、最初の失敗経路を返す。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        return self.evaluate_all_diagnostic_for_player(
            conditions,
            current_tick,
            graph,
            target_player_id=target_player_id,
        ).result

    def evaluate_all_diagnostic_for_player(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> ScenarioPredicateEvaluation:
        """対象者文脈の暗黙ANDを一度だけ評価し、確率判断も返す。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        decisions: list[ProbabilityDecision] = []
        result = self._evaluate_all(
            conditions,
            current_tick,
            graph,
            target_player_id,
            current_path=(),
            probability_decisions=decisions,
        )
        return ScenarioPredicateEvaluation(result, tuple(decisions))

    @staticmethod
    def _as_legacy_bool(
        result: PredicateResult[ScenarioEventCondition],
    ) -> bool:
        """構造化結果を既存bool APIへ射影し、phase未配線の例外を保つ。"""
        if "game_phase" in result.missing_context:
            raise RuntimeError("GAME_PHASE_IS requires game_phase_provider wiring")
        return result.is_satisfied

    def _evaluate_all(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        target_player_id: Optional[PlayerId],
        current_path: tuple[int, ...],
        probability_decisions: list[ProbabilityDecision],
    ) -> PredicateResult[ScenarioEventCondition]:
        for index, condition in enumerate(conditions):
            result = self._evaluate(
                condition,
                current_tick,
                graph,
                target_player_id,
                current_path=(*current_path, index),
                probability_decisions=probability_decisions,
            )
            if not result.is_satisfied:
                return self._prefix_failed_path(result, index)
        return PredicateResult.satisfied()

    @staticmethod
    def _prefix_failed_path(
        result: PredicateResult[ScenarioEventCondition],
        index: int,
    ) -> PredicateResult[ScenarioEventCondition]:
        if result.is_satisfied or result.failed_path is None:
            raise RuntimeError("only failed predicate results have a path")
        return PredicateResult(
            is_satisfied=False,
            reason_code=result.reason_code,
            failure_message=result.failure_message,
            failed_predicate=result.failed_predicate,
            failed_path=(index, *result.failed_path),
            missing_context=result.missing_context,
        )

    @staticmethod
    def _not_satisfied(
        condition: ScenarioEventCondition,
    ) -> PredicateResult[ScenarioEventCondition]:
        return PredicateResult.not_satisfied(
            failed_predicate=condition,
            failed_path=(),
        )

    @staticmethod
    def _map_common_result(
        result: PredicateResult[object],
        condition: ScenarioEventCondition,
    ) -> PredicateResult[ScenarioEventCondition]:
        """共通核の詳細を保ったまま、失敗述語を旧DTOへ写し戻す。"""
        if result.is_satisfied:
            return PredicateResult.satisfied()
        return PredicateResult(
            is_satisfied=False,
            reason_code=result.reason_code,
            failure_message=result.failure_message,
            failed_predicate=condition,
            failed_path=(),
            missing_context=result.missing_context,
        )

    @staticmethod
    def _missing_context(
        condition: ScenarioEventCondition,
        *context_names: str,
    ) -> PredicateResult[ScenarioEventCondition]:
        return PredicateResult.context_missing(
            failed_predicate=condition,
            failed_path=(),
            required_context=set(context_names),
        )

    def _evaluate(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        target_player_id: Optional[PlayerId],
        current_path: tuple[int, ...],
        probability_decisions: list[ProbabilityDecision],
    ) -> PredicateResult[ScenarioEventCondition]:
        ctype = cond.condition_type
        # 合成条件
        if ctype == "NOT":
            child_result = self._evaluate(
                cond.children[0],
                current_tick,
                graph,
                target_player_id,
                current_path=(*current_path, 0),
                probability_decisions=probability_decisions,
            )
            if child_result.is_satisfied:
                return self._not_satisfied(cond)
            if child_result.reason_code is PredicateReasonCode.NOT_SATISFIED:
                return PredicateResult.satisfied()
            return self._prefix_failed_path(child_result, 0)
        if ctype == "AND":
            return self._evaluate_all(
                cond.children,
                current_tick,
                graph,
                target_player_id,
                current_path=current_path,
                probability_decisions=probability_decisions,
            )
        if ctype == "OR":
            first_indeterminate = None
            for index, child in enumerate(cond.children):
                child_result = self._evaluate(
                    child,
                    current_tick,
                    graph,
                    target_player_id,
                    current_path=(*current_path, index),
                    probability_decisions=probability_decisions,
                )
                if child_result.is_satisfied:
                    return PredicateResult.satisfied()
                if (
                    first_indeterminate is None
                    and child_result.reason_code
                    is not PredicateReasonCode.NOT_SATISFIED
                ):
                    first_indeterminate = self._prefix_failed_path(
                        child_result, index,
                    )
            if first_indeterminate is not None:
                return first_indeterminate
            return self._not_satisfied(cond)
        # leaf 条件
        # Phase D-1: PROBABILITY は他の leaf より先に処理する。理由は (a) 他の
        # 軸とは独立に毎評価で random を消費するので順序を明確にする (b) 評価
        # コストが高い state lookup を不要に走らせない。
        if ctype == "PROBABILITY":
            # __post_init__ で probability が None / 範囲外なら弾かれているので
            # ここでは float() しても安全。
            probability = float(cond.probability)
            sampled_value = self._random.random()
            matched = sampled_value < probability
            probability_decisions.append(
                ProbabilityDecision(
                    path=current_path,
                    probability=probability,
                    sampled_value=sampled_value,
                    is_satisfied=matched,
                )
            )
            return (
                PredicateResult.satisfied()
                if matched
                else self._not_satisfied(cond)
            )
        world_flags = self._world_flag_state.as_frozen_set()
        if ctype == "TICK_AT_LEAST":
            if cond.tick is None:
                return self._not_satisfied(cond)
            common_result = self._predicate_evaluator.evaluate(
                TickAtLeastPredicate(int(cond.tick)),
                TickPredicateContext(current_tick),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "TICK_BETWEEN":
            if cond.tick_start is None or cond.tick_end is None:
                return self._not_satisfied(cond)
            matched = int(cond.tick_start) <= current_tick.value <= int(cond.tick_end)
            return PredicateResult.satisfied() if matched else self._not_satisfied(cond)
        if ctype == "FLAG_SET":
            if not cond.flag_name:
                return self._not_satisfied(cond)
            common_result = self._predicate_evaluator.evaluate(
                FlagSetPredicate(cond.flag_name),
                WorldFlagPredicateContext(world_flags),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "FLAG_NOT_SET":
            if not cond.flag_name:
                return self._not_satisfied(cond)
            common_result = self._predicate_evaluator.evaluate(
                FlagSetPredicate(cond.flag_name),
                WorldFlagPredicateContext(world_flags),
            )
            if common_result.is_satisfied:
                return self._not_satisfied(cond)
            if common_result.reason_code is PredicateReasonCode.NOT_SATISFIED:
                return PredicateResult.satisfied()
            return self._map_common_result(common_result, cond)
        if ctype == "PLAYER_AT_SPOT":
            if cond.spot_id is None:
                return self._not_satisfied(cond)
            spot_id = SpotId.create(cond.spot_id)
            placement_context = EntityPlacementPredicateContext(
                graph.entity_spot_mapping()
            )
            if target_player_id is not None:
                common_result = self._predicate_evaluator.evaluate(
                    EntityAtSpotPredicate(
                        EntityId.create(int(target_player_id)), spot_id,
                    ),
                    placement_context,
                )
                return self._map_common_result(common_result, cond)
            # 世界条件の既存意味は「誰かが居る」。scenario_event / reactive
            # binding は対象者を渡さないため、この分岐を従来どおり保つ。
            common_result = self._predicate_evaluator.evaluate(
                EntityCountAtSpotAtLeastPredicate(spot_id, 1),
                placement_context,
            )
            return self._map_common_result(common_result, cond)
        if ctype == "PLAYERS_AT_SPOT":
            # loader は spot_id の欠落と required_player_count の型・非正数を
            # 読み込み時に拒否する。以下の False は、loader を通さず value
            # object を直接組み立てるテスト・内部利用に対する防御であり、
            # 不正なシナリオを「条件不成立」へ縮退させる経路ではない。
            if cond.spot_id is None:
                return self._not_satisfied(cond)
            required = cond.required_player_count
            if (
                isinstance(required, bool)
                or (required is not None and not isinstance(required, int))
                or (required is not None and required <= 0)
            ):
                return self._not_satisfied(cond)
            # interaction 側と同じ既定値を旧入口で解決する。共通核は通常entity
            # の在席数だけを判定し、「player」という用途固有名を持たない。
            required_count = (
                required
                if required is not None
                else DEFAULT_REQUIRED_PLAYER_COUNT
            )
            common_result = self._predicate_evaluator.evaluate(
                EntityCountAtSpotAtLeastPredicate(
                    SpotId.create(cond.spot_id), required_count,
                ),
                EntityPlacementPredicateContext(graph.entity_spot_mapping()),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "GAME_PHASE_IS":
            if not cond.game_phase:
                return self._not_satisfied(cond)
            if self._game_phase_provider is None:
                return self._missing_context(cond, "game_phase")
            matched = self._game_phase_provider().value == cond.game_phase
            return PredicateResult.satisfied() if matched else self._not_satisfied(cond)
        if ctype == "OBJECT_STATE":
            if cond.object_id is None or cond.required_state is None:
                return self._not_satisfied(cond)
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return self._missing_context(cond, "spot_object")
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(obj.state),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "HAS_ITEM":
            if (
                not isinstance(cond.item_spec_id, int)
                or cond.item_spec_id <= 0
            ):
                return self._not_satisfied(cond)
            target_spec = ItemSpecId.create(cond.item_spec_id)
            if target_player_id is not None:
                inv = self._player_inventory_repository.find_by_id(target_player_id)
                if inv is None:
                    return self._missing_context(cond, "player_inventory")
                owned = collect_owned_item_spec_ids_from_inventory(
                    inv, self._item_repository
                )
                common_result = self._predicate_evaluator.evaluate(
                    ItemSpecOwnedPredicate(target_spec),
                    OwnedItemSpecsPredicateContext(owned),
                )
                return self._map_common_result(common_result, cond)
            missing_inventory = False
            indeterminate_result: PredicateResult[object] | None = None
            for status in self._player_status_repository.find_all():
                inv = self._player_inventory_repository.find_by_id(status.player_id)
                if inv is None:
                    missing_inventory = True
                    continue
                owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
                common_result = self._predicate_evaluator.evaluate(
                    ItemSpecOwnedPredicate(target_spec),
                    OwnedItemSpecsPredicateContext(owned),
                )
                if common_result.is_satisfied:
                    return PredicateResult.satisfied()
                if common_result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE:
                    return self._map_common_result(common_result, cond)
                if common_result.reason_code is not PredicateReasonCode.NOT_SATISFIED:
                    indeterminate_result = indeterminate_result or common_result
            if missing_inventory:
                return self._missing_context(cond, "player_inventory")
            if indeterminate_result is not None:
                return self._map_common_result(indeterminate_result, cond)
            return self._not_satisfied(cond)
        if ctype == "TICK_MODULO":
            if cond.tick_modulo is None or cond.tick_modulo <= 0:
                return self._not_satisfied(cond)
            phase = cond.tick_phase or 0
            matched = current_tick.value % cond.tick_modulo == phase
            return PredicateResult.satisfied() if matched else self._not_satisfied(cond)
        if ctype == "WEATHER_IS":
            # WEATHER_IS: 現在の天候タイプが weather_type と一致するか判定する。
            # provider 不在は天候不一致とは区別し、文脈不足として返す。
            # provider 呼び出しの例外は隠蔽せず caller のバグとして surface する。
            if not cond.weather_type:
                return self._not_satisfied(cond)
            if self._weather_state_provider is None:
                return self._missing_context(cond, "weather_state")
            state = self._weather_state_provider()
            try:
                required_weather = WeatherTypeEnum(cond.weather_type)
                current_weather = WeatherTypeEnum(state.weather_type.value)
            except (TypeError, ValueError):
                # loaderを迂回した不正DTO/providerは、型付き核へは渡さず、
                # 共通化前と同じ文字列の完全一致で互換性を保つ。
                return (
                    PredicateResult.satisfied()
                    if state.weather_type.value == cond.weather_type
                    else self._not_satisfied(cond)
                )
            common_result = self._predicate_evaluator.evaluate(
                WeatherTypeIsPredicate(required_weather),
                WeatherTypePredicateContext(current_weather),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "OBJECT_STATE_TICK_AT_LEAST":
            # 「対象 object の state[state_key] が tick 値で、そこから
            # ticks_offset 経過したか」を判定する。state_key の値は int 想定。
            # state_key が無い / 値が None の場合は「まだ起きていない」と
            # 解釈し、`treat_missing_as_passed` フラグで True/False を選ぶ
            # （default False = 経過判定不能なので fire しない）。
            # 値が int でも None でもない場合は作家ミスの可能性があるので
            # 警告ログを出して False。
            if (
                cond.object_id is None
                or not cond.state_key
                or cond.ticks_offset is None
            ):
                return self._not_satisfied(cond)
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return self._missing_context(cond, "spot_object")
            recorded_tick = obj.state.get(cond.state_key)
            if recorded_tick is None:
                # 「まだ起きていない」 sentinel。作家が `treat_missing_as_passed`
                # で意味を選択する。silent fallback を避けるためフラグを default
                # False（保守的）にしてある。
                return (
                    PredicateResult.satisfied()
                    if cond.treat_missing_as_passed
                    else self._not_satisfied(cond)
                )
            if not isinstance(recorded_tick, int):
                # シナリオ作家が int でも None でもない値（文字列など）を
                # 入れていたケース。デバッグ困難になるので警告を出す。
                _logger.warning(
                    "OBJECT_STATE_TICK_AT_LEAST: state[%r] is not int or None "
                    "(got %s) for object_id=%s",
                    cond.state_key,
                    type(recorded_tick).__name__,
                    cond.object_id,
                )
                return self._not_satisfied(cond)
            matched = current_tick.value >= recorded_tick + int(cond.ticks_offset)
            return PredicateResult.satisfied() if matched else self._not_satisfied(cond)
        if ctype == "OBJECT_STATE_INT_AT_LEAST":
            # state[state_key] の整数値が threshold (= ticks_offset を流用) 以上か。
            # 採取の枯渇 (count >= N で永久に available=false) の判定に使う。
            # state_key 不在 / 値が int 以外 → 0 扱いで判定 (= 「まだ採取してない」状態)。
            if cond.object_id is None or not cond.state_key or cond.ticks_offset is None:
                return self._not_satisfied(cond)
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return self._missing_context(cond, "spot_object")
            common_result = self._predicate_evaluator.evaluate(
                StateIntAtLeastPredicate(
                    state_key=cond.state_key,
                    threshold=int(cond.ticks_offset),
                ),
                StateValuesPredicateContext(obj.state),
            )
            return self._map_common_result(common_result, cond)
        if ctype == "OBJECT_STATE_INT_GREATER_THAN_OTHER":
            # 2 つの object.state の整数値を比べ、左辺が**厳密に大きい**ときだけ
            # 成立する。「東の祭壇の納品数 > 西の祭壇の納品数」の判定用。
            # 同値は不成立 (引き分けは両側の条件がどちらも成立しない形で表す)。
            # state_key 不在 / 値が int 以外は 0 扱い (= まだ何も納めていない)。
            if (
                cond.object_id is None
                or not cond.state_key
                or cond.other_object_id is None
                or not cond.other_state_key
            ):
                return self._not_satisfied(cond)
            left_obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph,
                self._spot_interior_repository,
            )
            right_obj = find_object_in_graph(
                SpotObjectId.create(cond.other_object_id), graph,
                self._spot_interior_repository,
            )
            if left_obj is None or right_obj is None:
                return self._missing_context(cond, "spot_object")

            def _int_state(obj: Any, key: str) -> int:
                value = obj.state.get(key, 0)
                return value if isinstance(value, int) else 0

            matched = (
                _int_state(left_obj, cond.state_key)
                > _int_state(right_obj, cond.other_state_key)
            )
            return (
                PredicateResult.satisfied() if matched else self._not_satisfied(cond)
            )
        # loader を迂回して未知の条件が渡った場合も、通常不一致へ潰さない。
        return PredicateResult.unsupported(
            failed_predicate=cond,
            failed_path=(),
        )
