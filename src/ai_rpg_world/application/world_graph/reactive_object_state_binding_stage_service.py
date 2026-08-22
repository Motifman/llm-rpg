"""ReactiveObjectStateBinding の毎 tick 評価ステージ。

各 binding を評価し、predicate の真偽に応じて対象オブジェクトの state に
on_true_state_updates / on_false_state_updates をマージする（部分上書き）。
state が変わらないときは interior を save しない（副作用最小化）。

`ReactivePassageBindingStageService` の object 状態版。実装パターンは
ほぼ同じで、対象が SpotConnection.passage か SpotObject.state かの違い。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Tuple, TYPE_CHECKING

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
)
from ai_rpg_world.application.world_graph.spot_object_lookup import find_object_with_owner
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    StateDeltaEntry,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.reactive_command_repository_provider import (
        ReactiveCommandRepositoryProviderPort,
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
        predicate_trace_emitter: ScenarioPredicateTraceEmitter | None = None,
        command_scope_factory: (
            "CommandScopeFactoryPort[ReactiveCommandRepositoryProviderPort] | None"
        ) = None,
    ) -> None:
        self._bindings = tuple(bindings)
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._condition_evaluator = condition_evaluator
        self._predicate_trace_emitter = predicate_trace_emitter
        self._command_scope_factory = command_scope_factory
        self._condition_evaluator.validate_dependencies(
            binding.predicate for binding in self._bindings
        )

    def run(self, current_tick: WorldTick) -> None:
        if not self._bindings:
            return
        if self._command_scope_factory is not None:
            for binding_index, binding in enumerate(self._bindings):
                with self._command_scope_factory.create() as context:
                    repositories = context.repositories
                    graph = repositories.spot_graph.find_graph()
                    existing_events = tuple(graph.get_events())
                    self._apply_binding(
                        binding,
                        binding_index,
                        current_tick,
                        graph,
                        spot_interior_repository=repositories.spot_interiors,
                    )
                    self._collect_new_graph_events(
                        graph,
                        existing_events,
                        context,
                    )
            return
        graph = self._spot_graph_repository.find_graph()
        # 同じ owner spot に属する binding を 1 度の interior 取得 + save に
        # まとめるため、interior_id ごとに変更された object をバッファする。
        # 実装簡略化のため、ここでは binding 1 件ごとに interior を取り直す
        # （binding 数が少ない前提）。
        for binding_index, binding in enumerate(self._bindings):
            self._apply_binding(
                binding,
                binding_index,
                current_tick,
                graph,
                spot_interior_repository=self._spot_interior_repository,
            )

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[ReactiveCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageをbinding 1件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def _apply_binding(
        self,
        binding: ReactiveObjectStateBinding,
        binding_index: int,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        spot_interior_repository: ISpotInteriorRepository,
    ) -> None:
        target, owner_spot = find_object_with_owner(
            binding.target_object_id, graph, spot_interior_repository,
        )
        if target is None or owner_spot is None:
            _logger.warning(
                "ReactiveObjectStateBinding: target object %s not found in any spot",
                binding.target_object_id.value,
            )
            return
        evaluation = self._condition_evaluator.evaluate_diagnostic(
            binding.predicate, current_tick, graph,
        )
        result = evaluation.result
        if self._predicate_trace_emitter is not None:
            self._predicate_trace_emitter.emit(
                evaluation=evaluation,
                root_condition_type=binding.predicate.condition_type,
                current_tick=current_tick,
                purpose="reactive_object_binding",
                owner_id=binding.target_object_id.value,
                owner_index=binding_index,
            )
        predicate_value = result.is_satisfied
        updates = binding.updates_for(predicate_value)
        # 既に同じ値が入っていれば save 不要。
        # asymmetric binding (Phase 2-B) で `updates={}` (片側が空 tuple)
        # のケースもここで自然に early return する: `all([])` は True なので
        # state を一切 touch せず save を発火しない。
        if all(target.state.get(k) == v for k, v in updates.items()):
            return
        old_state = dict(target.state)
        new_state = dict(target.state)
        for k, v in updates.items():
            new_state[k] = v
        new_target = target.with_state(new_state)
        interior = spot_interior_repository.find_by_spot_id(owner_spot)
        if interior is None:
            return
        new_interior = interior.replace_object(new_target)
        spot_interior_repository.save(owner_spot, new_interior)
        # Issue #179: state が実際に変わったとき SpotObjectStateChangedEvent を
        # graph aggregate に積み、observation pipeline 経由で同 spot の
        # observer (= NPC / 残留 agent) に届ける。reactive 由来は actor 無し
        # なので actor_entity_id=None。
        delta = tuple(
            StateDeltaEntry(key=k, before=old_state.get(k), after=v)
            for k, v in updates.items()
            if old_state.get(k) != v
        )
        if delta:
            # 著者が宣言した narrative があれば formatter に渡す。
            # 無ければ None → formatter は observation を emit しない (silent)。
            # これにより「available が False から True に変わった」のような
            # 内部用語の漏洩を防ぐ。
            narrative = (
                binding.narrative_on_true
                if predicate_value
                else binding.narrative_on_false
            )
            graph.add_event(
                SpotObjectStateChangedEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    spot_id=owner_spot,
                    object_id=binding.target_object_id,
                    old_state=old_state,
                    new_state=new_state,
                    actor_entity_id=None,
                    state_delta=delta,
                    narrative=narrative,
                )
            )

    def _collect_new_graph_events(
        self,
        graph: SpotGraphAggregate,
        existing_events: tuple[Any, ...],
        context: "CommandContext[ReactiveCommandRepositoryProviderPort]",
    ) -> None:
        """このbindingが追加したeventだけを確定後配送へ移す。"""
        all_events = tuple(graph.get_events())
        new_events = all_events[len(existing_events):]
        if not new_events:
            return
        graph.clear_events()
        for event in existing_events:
            graph.add_event(event)
        context.repositories.spot_graph.save(graph)
        context.collect_all(new_events)

    @property
    def managed_state_keys_per_object(self) -> Mapping[int, Tuple[str, ...]]:
        """各 object_id → 管理する state キーのマップ（テスト/監査用）。"""
        return {
            b.target_object_id.value: b.managed_state_keys for b in self._bindings
        }
