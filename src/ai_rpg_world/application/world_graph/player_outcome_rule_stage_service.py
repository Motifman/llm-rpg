"""宣言されたプレイヤー個別結果を tick ごとに評価する段階。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Optional

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import (
    PlayerOutcomeRule,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )


_logger = logging.getLogger(__name__)
_PROGRESS_PREFIX = "player_outcome_rule:"
_CommittedOutcome = tuple[PlayerId, PlayerOutcomeEnum, PlayerOutcomeEnum]


class PlayerOutcomeRuleStageService:
    """規則の発火時に、適格な未確定プレイヤーの結果を確定する。"""

    def __init__(
        self,
        *,
        rules: Iterable[PlayerOutcomeRule],
        outcome_registry: PlayerOutcomeRegistry,
        condition_evaluator: ScenarioConditionEvaluator,
        progress_store: InMemorySpotGraphScenarioEventProgressStore,
        graph_provider: Callable[[], SpotGraphAggregate],
        player_ids: Sequence[PlayerId],
        predicate_trace_emitter: ScenarioPredicateTraceEmitter | None = None,
        command_scope_factory: Optional["CommandScopeFactoryPort[object]"] = None,
    ) -> None:
        self._rules = tuple(rules)
        self._outcome_registry = outcome_registry
        self._condition_evaluator = condition_evaluator
        self._progress_store = progress_store
        self._graph_provider = graph_provider
        self._player_ids = tuple(player_ids)
        self._predicate_trace_emitter = predicate_trace_emitter
        self._command_scope_factory = command_scope_factory
        self._condition_evaluator.validate_dependencies(
            condition
            for rule in self._rules
            for condition in (rule.trigger, *rule.player_conditions)
        )

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[object]",
    ) -> None:
        """本番stageを発火rule一件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        """発火条件を満たした規則を評価し、一度限りなら機会を消費する。"""
        if not self._rules:
            return
        for rule in self._rules:
            progress_id = f"{_PROGRESS_PREFIX}{rule.rule_id}"
            if rule.once and self._progress_store.is_fired(progress_id):
                continue
            if self._command_scope_factory is None:
                committed, fired = self._evaluate_and_apply(
                    rule,
                    current_tick,
                    notify_callbacks=True,
                )
                if fired:
                    self._log_committed(rule, current_tick, len(committed))
                continue
            self._run_rule_command(rule, current_tick)

    def _run_rule_command(
        self,
        rule: PlayerOutcomeRule,
        current_tick: WorldTick,
    ) -> None:
        """ruleの全対象outcomeと一度限り進捗を一緒に確定する。"""
        committed: tuple[_CommittedOutcome, ...] = ()
        fired = False
        try:
            with self._command_scope_factory.create():
                committed, fired = self._evaluate_and_apply(
                    rule,
                    current_tick,
                    notify_callbacks=False,
                )
        except CommandPostCommitException:
            self._notify_committed_outcomes(committed)
            if fired:
                self._log_committed(rule, current_tick, len(committed))
            raise
        self._notify_committed_outcomes(committed)
        if fired:
            self._log_committed(rule, current_tick, len(committed))

    def _evaluate_and_apply(
        self,
        rule: PlayerOutcomeRule,
        current_tick: WorldTick,
        *,
        notify_callbacks: bool,
    ) -> tuple[tuple[_CommittedOutcome, ...], bool]:
        # 外側の確認は不要なscope生成を避ける高速経路にすぎない。
        # 待機中に別commandが同じonce規則を確定し得るため、資源所有権を
        # 取得した後にも進捗を再確認してから条件評価へ進む。
        if rule.once and self._progress_store.is_fired(
            f"{_PROGRESS_PREFIX}{rule.rule_id}"
        ):
            return (), False

        graph = self._graph_provider()
        trigger_evaluation = self._condition_evaluator.evaluate_diagnostic(
            rule.trigger,
            current_tick,
            graph,
        )
        trigger_result = trigger_evaluation.result
        if self._predicate_trace_emitter is not None:
            self._predicate_trace_emitter.emit(
                evaluation=trigger_evaluation,
                root_condition_type=rule.trigger.condition_type,
                current_tick=current_tick,
                purpose="player_outcome_trigger",
                owner_id=rule.rule_id,
            )
        if not trigger_result.is_satisfied:
            return (), False

        committed: list[_CommittedOutcome] = []
        for player_id in self._player_ids:
            old_outcome = self._outcome_registry.get_outcome(player_id)
            if old_outcome.is_resolved:
                continue
            eligibility_evaluation = (
                self._condition_evaluator.evaluate_all_diagnostic_for_player(
                    rule.player_conditions,
                    current_tick,
                    graph,
                    target_player_id=player_id,
                )
            )
            eligibility_result = eligibility_evaluation.result
            if self._predicate_trace_emitter is not None:
                self._predicate_trace_emitter.emit(
                    evaluation=eligibility_evaluation,
                    root_condition_type="IMPLICIT_AND",
                    current_tick=current_tick,
                    purpose="player_outcome_eligibility",
                    owner_id=rule.rule_id,
                    player_id=player_id.value,
                )
            if not eligibility_result.is_satisfied:
                continue
            if self._outcome_registry.set_outcome(
                player_id,
                rule.outcome,
                notify_callbacks=notify_callbacks,
            ):
                committed.append((player_id, old_outcome, rule.outcome))

        # 発火条件は「機会が来たか」を表す。対象者が 0 人でも、救助船の
        # ような一度限りの機会を後から再利用できないよう消費済みにする。
        if rule.once:
            self._progress_store.mark_fired(f"{_PROGRESS_PREFIX}{rule.rule_id}")
        return tuple(committed), True

    def _notify_committed_outcomes(
        self,
        committed: tuple[_CommittedOutcome, ...],
    ) -> None:
        """確定したoutcomeだけを元のplayer順でcallbackへ通知する。"""
        for player_id, old_outcome, new_outcome in committed:
            self._outcome_registry.notify_outcome_change(
                player_id,
                old_outcome,
                new_outcome,
            )

    @staticmethod
    def _log_committed(
        rule: PlayerOutcomeRule,
        current_tick: WorldTick,
        resolved_count: int,
    ) -> None:
        _logger.info(
            "player_outcome_rule=%s fired at tick=%s: resolved %d player(s) as %s",
            rule.rule_id,
            current_tick.value,
            resolved_count,
            rule.outcome.value,
        )
