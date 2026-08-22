"""シナリオが宣言するプレイヤー個別結果の規則。"""

from dataclasses import dataclass

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PlayerOutcomeRuleValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


@dataclass(frozen=True)
class PlayerOutcomeRule:
    """発火機会と対象者の適格条件を分離した個人結果規則。

    ``trigger`` は規則を評価する時点、``player_conditions`` はその時点で
    結果を受ける未確定プレイヤーを表す。該当者が 0 人でも ``once`` の規則は
    発火済みにするため、両者を一つの条件列には畳まない。
    """

    rule_id: str
    trigger: ScenarioEventCondition
    player_conditions: tuple[ScenarioEventCondition, ...]
    outcome: PlayerOutcomeEnum
    once: bool

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.rule_id must be a non-empty string"
            )
        if not isinstance(self.trigger, ScenarioEventCondition):
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.trigger must be ScenarioEventCondition"
            )
        if not isinstance(self.player_conditions, tuple) or not all(
            isinstance(condition, ScenarioEventCondition)
            for condition in self.player_conditions
        ):
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.player_conditions must be a tuple of "
                "ScenarioEventCondition"
            )
        if not isinstance(self.outcome, PlayerOutcomeEnum):
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.outcome must be PlayerOutcomeEnum"
            )
        if self.outcome not in (
            PlayerOutcomeEnum.RESCUED,
            PlayerOutcomeEnum.STRANDED,
        ):
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.outcome must be RESCUED or STRANDED"
            )
        if not isinstance(self.once, bool):
            raise PlayerOutcomeRuleValidationException(
                "PlayerOutcomeRule.once must be bool"
            )
