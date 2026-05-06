"""ReactiveObjectStateBinding の毎 tick 評価ステージ。

各 binding を評価し、predicate の真偽に応じて対象オブジェクトの state に
on_true_state_updates / on_false_state_updates をマージする（部分上書き）。
state が変わらないときは interior を save しない（副作用最小化）。

`ReactivePassageBindingStageService` の object 状態版。実装パターンは
ほぼ同じで、対象が SpotConnection.passage か SpotObject.state かの違い。
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Tuple

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.spot_object_lookup import find_object_with_owner
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)


_logger = logging.getLogger(__name__)


class ReactiveObjectStateBindingStageService:
    """毎 tick 全 binding を評価し、対象 object.state を反映する。"""

    def __init__(
        self,
        *,
        bindings: Iterable[ReactiveObjectStateBinding],
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        condition_evaluator: ScenarioConditionEvaluator,
    ) -> None:
        self._bindings = tuple(bindings)
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._condition_evaluator = condition_evaluator

    def run(self, current_tick: WorldTick) -> None:
        if not self._bindings:
            return
        graph = self._spot_graph_repository.find_graph()
        # 同じ owner spot に属する binding を 1 度の interior 取得 + save に
        # まとめるため、interior_id ごとに変更された object をバッファする。
        # 実装簡略化のため、ここでは binding 1 件ごとに interior を取り直す
        # （binding 数が少ない前提）。
        for binding in self._bindings:
            self._apply_binding(binding, current_tick, graph)

    def _apply_binding(
        self,
        binding: ReactiveObjectStateBinding,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> None:
        target, owner_spot = find_object_with_owner(
            binding.target_object_id, graph, self._spot_interior_repository,
        )
        if target is None or owner_spot is None:
            _logger.warning(
                "ReactiveObjectStateBinding: target object %s not found in any spot",
                binding.target_object_id.value,
            )
            return
        predicate_value = self._condition_evaluator.evaluate(
            binding.predicate, current_tick, graph,
        )
        updates = binding.updates_for(predicate_value)
        # 既に同じ値が入っていれば save 不要。
        # asymmetric binding (Phase 2-B) で `updates={}` (片側が空 tuple)
        # のケースもここで自然に early return する: `all([])` は True なので
        # state を一切 touch せず save を発火しない。
        if all(target.state.get(k) == v for k, v in updates.items()):
            return
        new_state = dict(target.state)
        for k, v in updates.items():
            new_state[k] = v
        new_target = target.with_state(new_state)
        interior = self._spot_interior_repository.find_by_spot_id(owner_spot)
        if interior is None:
            return
        new_interior = interior.replace_object(new_target)
        self._spot_interior_repository.save(owner_spot, new_interior)

    @property
    def managed_state_keys_per_object(self) -> Mapping[int, Tuple[str, ...]]:
        """各 object_id → 管理する state キーのマップ（テスト/監査用）。"""
        return {
            b.target_object_id.value: b.managed_state_keys for b in self._bindings
        }
