"""宣言されたプレイヤー個別結果を tick ごとに評価する段階。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.domain.common.value_object import WorldTick
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


_logger = logging.getLogger(__name__)
_PROGRESS_PREFIX = "player_outcome_rule:"


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
    ) -> None:
        self._rules = tuple(rules)
        self._outcome_registry = outcome_registry
        self._condition_evaluator = condition_evaluator
        self._progress_store = progress_store
        self._graph_provider = graph_provider
        self._player_ids = tuple(player_ids)
        self._condition_evaluator.validate_dependencies(
            condition
            for rule in self._rules
            for condition in (rule.trigger, *rule.player_conditions)
        )

    def run(self, current_tick: WorldTick) -> None:
        """発火条件を満たした規則を評価し、一度限りなら機会を消費する。"""
        if not self._rules:
            return
        graph = self._graph_provider()
        for rule in self._rules:
            progress_id = f"{_PROGRESS_PREFIX}{rule.rule_id}"
            if rule.once and self._progress_store.is_fired(progress_id):
                continue
            if not self._condition_evaluator.evaluate(
                rule.trigger,
                current_tick,
                graph,
            ):
                continue

            resolved_count = 0
            for player_id in self._player_ids:
                if self._outcome_registry.get_outcome(player_id).is_resolved:
                    continue
                if not self._condition_evaluator.evaluate_all_for_player(
                    rule.player_conditions,
                    current_tick,
                    graph,
                    target_player_id=player_id,
                ):
                    continue
                if self._outcome_registry.set_outcome(player_id, rule.outcome):
                    resolved_count += 1

            # 発火条件は「機会が来たか」を表す。対象者が 0 人でも、救助船の
            # ような一度限りの機会を後から再利用できないよう消費済みにする。
            if rule.once:
                self._progress_store.mark_fired(progress_id)
            _logger.info(
                "player_outcome_rule=%s fired at tick=%s: resolved %d player(s) as %s",
                rule.rule_id,
                current_tick.value,
                resolved_count,
                rule.outcome.value,
            )
