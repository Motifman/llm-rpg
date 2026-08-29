"""PlayerOutcomeRule が結果規則の不変条件を構築時に保証することを検証する。"""

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PlayerOutcomeRuleValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import (
    PlayerOutcomeRule,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


_TRIGGER = ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=10)


def _rule(**overrides) -> PlayerOutcomeRule:
    values = {
        "rule_id": "rescue_ship_10",
        "trigger": _TRIGGER,
        "player_conditions": (),
        "outcome": PlayerOutcomeEnum.RESCUED,
        "once": True,
    }
    values.update(overrides)
    return PlayerOutcomeRule(**values)


class TestPlayerOutcomeRuleValidation:
    """終局結果だけを、明示した発火機会と対象者条件へ結び付けられる。"""

    def test_accepts_resolved_outcome_with_empty_player_conditions(self) -> None:
        """未確定者全員を対象にするための空条件列は有効な宣言である。"""
        assert _rule().player_conditions == ()

    @pytest.mark.parametrize(
        ("field", "invalid"),
        [
            ("rule_id", ""),
            ("trigger", None),
            ("player_conditions", []),
            ("once", "true"),
        ],
    )
    def test_rejects_malformed_fields(self, field: str, invalid: object) -> None:
        """識別子・trigger・条件 tuple・once の型違反は値オブジェクトが拒否する。"""
        with pytest.raises(PlayerOutcomeRuleValidationException, match=field):
            _rule(**{field: invalid})

    @pytest.mark.parametrize(
        "outcome",
        [
            PlayerOutcomeEnum.UNRESOLVED,
            PlayerOutcomeEnum.DEAD,
            PlayerOutcomeEnum.EJECTED,
        ],
    )
    def test_rejects_outcomes_that_require_other_world_state(
        self,
        outcome: PlayerOutcomeEnum,
    ) -> None:
        """規則だけでは世界状態を完結できない未確定・死亡・追放を拒否する。"""
        with pytest.raises(
            PlayerOutcomeRuleValidationException,
            match="RESCUED or STRANDED",
        ):
            _rule(outcome=outcome)
