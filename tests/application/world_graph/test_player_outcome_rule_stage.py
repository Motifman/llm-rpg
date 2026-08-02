"""宣言された個人結果規則を tick ごとに評価する段階の仕様。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.player_outcome_rule_stage_service import (
    PlayerOutcomeRuleStageService,
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
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import (
    PlayerOutcomeRule,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


def _rule(*, once: bool = True) -> PlayerOutcomeRule:
    return PlayerOutcomeRule(
        rule_id="rescue_ship",
        trigger=ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=10),
        player_conditions=(
            ScenarioEventCondition(condition_type="PLAYER_AT_SPOT", spot_id=100),
        ),
        outcome=PlayerOutcomeEnum.RESCUED,
        once=once,
    )


def _stage(
    *,
    evaluator: MagicMock,
    progress: InMemorySpotGraphScenarioEventProgressStore | None = None,
    once: bool = True,
) -> tuple[PlayerOutcomeRuleStageService, PlayerOutcomeRegistry]:
    player_ids = (PlayerId(1), PlayerId(2))
    registry = PlayerOutcomeRegistry.new_for_players(list(player_ids))
    return (
        PlayerOutcomeRuleStageService(
            rules=(_rule(once=once),),
            outcome_registry=registry,
            condition_evaluator=evaluator,
            progress_store=(
                progress or InMemorySpotGraphScenarioEventProgressStore()
            ),
            graph_provider=MagicMock(return_value=MagicMock()),
            player_ids=player_ids,
        ),
        registry,
    )


class TestPlayerOutcomeRuleStage:
    """発火機会・対象者条件・一度限りの進捗を別々に扱う。"""

    def test_false_trigger_does_not_evaluate_players_or_consume_rule(self) -> None:
        """発火条件が偽なら対象者を調べず、後の tick で再評価できる。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = False
        progress = InMemorySpotGraphScenarioEventProgressStore()
        stage, registry = _stage(evaluator=evaluator, progress=progress)

        stage.run(WorldTick(9))

        evaluator.evaluate_all_for_player.assert_not_called()
        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED
        assert not progress.is_fired("player_outcome_rule:rescue_ship")

    def test_true_trigger_resolves_only_eligible_unresolved_players(self) -> None:
        """発火時は各未確定者を本人の文脈で評価し、適格者だけを確定する。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = True
        evaluator.evaluate_all_for_player.side_effect = lambda *args, **kwargs: (
            kwargs["target_player_id"] == PlayerId(1)
        )
        stage, registry = _stage(evaluator=evaluator)

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        assert registry.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED

    def test_once_rule_is_consumed_even_when_no_player_is_eligible(self) -> None:
        """一度限りの機会は該当者がゼロでも消費し、後から条件を満たしても再発火しない。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = True
        evaluator.evaluate_all_for_player.return_value = False
        progress = InMemorySpotGraphScenarioEventProgressStore()
        stage, registry = _stage(evaluator=evaluator, progress=progress)

        stage.run(WorldTick(10))
        evaluator.evaluate_all_for_player.return_value = True
        stage.run(WorldTick(11))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED
        assert progress.is_fired("player_outcome_rule:rescue_ship")

    def test_repeating_rule_can_resolve_a_player_who_becomes_eligible_later(self) -> None:
        """once=false なら未適格だった未確定者を次の tick でも評価する。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = True
        evaluator.evaluate_all_for_player.return_value = False
        stage, registry = _stage(evaluator=evaluator, once=False)

        stage.run(WorldTick(10))
        evaluator.evaluate_all_for_player.return_value = True
        stage.run(WorldTick(11))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        assert registry.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.RESCUED

    def test_resolved_player_is_not_re_evaluated_or_overwritten(self) -> None:
        """既に確定した結果は対象者評価から除外し、別の結果で上書きしない。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = True
        evaluator.evaluate_all_for_player.return_value = True
        stage, registry = _stage(evaluator=evaluator)
        registry.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD
        evaluated = [
            call.kwargs["target_player_id"]
            for call in evaluator.evaluate_all_for_player.call_args_list
        ]
        assert evaluated == [PlayerId(2)]

    def test_rule_progress_is_namespaced_from_scenario_event_ids(self) -> None:
        """同名の scenario_event が発火済みでも個人結果規則の機会を奪わない。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = True
        evaluator.evaluate_all_for_player.return_value = True
        progress = InMemorySpotGraphScenarioEventProgressStore()
        progress.mark_fired("rescue_ship")
        stage, registry = _stage(evaluator=evaluator, progress=progress)

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        assert progress.is_fired("player_outcome_rule:rescue_ship")
