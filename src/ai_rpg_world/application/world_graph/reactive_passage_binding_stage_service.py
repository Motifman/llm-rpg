"""ReactivePassageBinding の毎 tick 評価ステージ。

各 binding を評価し、predicate の真偽に応じて対象接続の passage state を
on_true_state / on_false_state に切り替える。状態が変わらないときは
SpotGraphAggregate.set_connection_passage_state が冪等なのでイベントは出ない。
"""

from __future__ import annotations

from typing import Any, Iterable, TYPE_CHECKING

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
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

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.reactive_command_repository_provider import (
        ReactiveCommandRepositoryProviderPort,
    )


class ReactivePassageBindingStageService:
    """毎 tick で全 binding を評価し、対象接続の passage 状態を更新する。"""

    def __init__(
        self,
        *,
        bindings: Iterable[ReactivePassageBinding],
        spot_graph_repository: ISpotGraphRepository,
        condition_evaluator: ScenarioConditionEvaluator,
        predicate_trace_emitter: ScenarioPredicateTraceEmitter | None = None,
        command_scope_factory: (
            "CommandScopeFactoryPort[ReactiveCommandRepositoryProviderPort] | None"
        ) = None,
    ) -> None:
        self._bindings = tuple(bindings)
        self._spot_graph_repository = spot_graph_repository
        self._condition_evaluator = condition_evaluator
        self._predicate_trace_emitter = predicate_trace_emitter
        self._command_scope_factory = command_scope_factory
        self._condition_evaluator.validate_dependencies(
            binding.predicate for binding in self._bindings
        )

    def run(self, current_tick: WorldTick) -> None:
        if not self._bindings:
            return
        if self._command_scope_factory is None:
            self._run_with_repository(
                current_tick,
                spot_graph_repository=self._spot_graph_repository,
            )
            return
        with self._command_scope_factory.create() as context:
            self._run_with_repository(
                current_tick,
                spot_graph_repository=context.repositories.spot_graph,
                context=context,
            )

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[ReactiveCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageを全binding共通の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def _run_with_repository(
        self,
        current_tick: WorldTick,
        *,
        spot_graph_repository: ISpotGraphRepository,
        context: "CommandContext[ReactiveCommandRepositoryProviderPort] | None" = None,
    ) -> None:
        graph = spot_graph_repository.find_graph()
        existing_events = tuple(graph.get_events())
        graph_dirty = False
        logical_connection_keys: dict[int, tuple[int, ...]] = {}
        for record in graph.iter_connection_records():
            forward = int(record.connection.connection_id.value)
            if record.reverse_connection_id is None:
                logical_connection_keys[forward] = (forward,)
                continue
            reverse = int(record.reverse_connection_id.value)
            pair = tuple(sorted((forward, reverse)))
            logical_connection_keys[forward] = pair
            logical_connection_keys[reverse] = pair
        emitted_transitions: set[tuple[tuple[int, ...], str]] = set()
        for binding_index, binding in enumerate(self._bindings):
            target_state = self._target_state_for(
                binding, binding_index, current_tick, graph,
            )
            conn = graph.get_connection(binding.target_connection_id)
            # 既に目標 state ならスキップ。set_connection_passage_state 自体も
            # 冪等だが、kind 不整合などの with_state バリデーションを毎 tick
            # 走らせない方が無駄が無い。
            if conn.passage.state == target_state:
                continue
            logical_key = logical_connection_keys.get(
                int(binding.target_connection_id.value),
                (int(binding.target_connection_id.value),),
            )
            transition_key = (logical_key, target_state)
            emitted = graph.set_connection_passage_state(
                binding.target_connection_id,
                target_state,
                cause=PassageChangeCauseEnum.REACTIVE,
                # Issue #183: 世界 tick 由来の自動評価なので actor は不在。
                # 明示的に None を渡し、将来 actor を埋めようとした設計ミスを防ぐ。
                actor_entity_id=None,
                # 双方向接続は正逆 2 本を同じ状態へ動かすが、世界で起きた
                # 変化は 1 つ。同じ stage 内で先に片側が通知済みなら、逆向きは
                # 状態だけ同期し、同じ観測を重ねない。
                emit_state_change_event=transition_key not in emitted_transitions,
            )
            if emitted:
                emitted_transitions.add(transition_key)
            graph_dirty = True
        if graph_dirty:
            new_events: tuple[Any, ...] = ()
            if context is not None:
                all_events = tuple(graph.get_events())
                new_events = all_events[len(existing_events):]
                graph.clear_events()
                for event in existing_events:
                    graph.add_event(event)
            spot_graph_repository.save(graph)
            if context is not None:
                context.collect_all(new_events)

    def _target_state_for(
        self,
        binding: ReactivePassageBinding,
        binding_index: int,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> str:
        evaluation = self._condition_evaluator.evaluate_diagnostic(
            binding.predicate, current_tick, graph,
        )
        result = evaluation.result
        if self._predicate_trace_emitter is not None:
            self._predicate_trace_emitter.emit(
                evaluation=evaluation,
                root_condition_type=binding.predicate.condition_type,
                current_tick=current_tick,
                purpose="reactive_passage_binding",
                owner_id=binding.target_connection_id.value,
                owner_index=binding_index,
            )
        return binding.on_true_state if result.is_satisfied else binding.on_false_state
