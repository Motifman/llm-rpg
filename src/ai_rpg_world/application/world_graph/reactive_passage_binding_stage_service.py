"""ReactivePassageBinding の毎 tick 評価ステージ。

各 binding を評価し、predicate の真偽に応じて対象接続の passage state を
on_true_state / on_false_state に切り替える。状態が変わらないときは
SpotGraphAggregate.set_connection_passage_state が冪等なのでイベントは出ない。
"""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)


class ReactivePassageBindingStageService:
    """毎 tick で全 binding を評価し、対象接続の passage 状態を更新する。"""

    def __init__(
        self,
        *,
        bindings: Iterable[ReactivePassageBinding],
        spot_graph_repository: ISpotGraphRepository,
        condition_evaluator: ScenarioConditionEvaluator,
    ) -> None:
        self._bindings = tuple(bindings)
        self._spot_graph_repository = spot_graph_repository
        self._condition_evaluator = condition_evaluator

    def run(self, current_tick: WorldTick) -> None:
        if not self._bindings:
            return
        graph = self._spot_graph_repository.find_graph()
        graph_dirty = False
        for binding in self._bindings:
            target_state = self._target_state_for(binding, current_tick, graph)
            conn = graph.get_connection(binding.target_connection_id)
            # 既に目標 state ならスキップ。set_connection_passage_state 自体も
            # 冪等だが、kind 不整合などの with_state バリデーションを毎 tick
            # 走らせない方が無駄が無い。
            if conn.passage.state == target_state:
                continue
            graph.set_connection_passage_state(
                binding.target_connection_id,
                target_state,
                cause=PassageChangeCauseEnum.REACTIVE,
            )
            graph_dirty = True
        if graph_dirty:
            self._spot_graph_repository.save(graph)

    def _target_state_for(
        self,
        binding: ReactivePassageBinding,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> str:
        predicate_true = self._condition_evaluator.evaluate(
            binding.predicate, current_tick, graph,
        )
        return binding.on_true_state if predicate_true else binding.on_false_state
