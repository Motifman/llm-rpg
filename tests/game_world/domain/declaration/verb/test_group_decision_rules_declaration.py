from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupDecisionId
from tests.game_world.support.verb_declarations_for_tests import as_declared_group_decision_rules, everyone_votes_on


class TestGroupDecisionRulesDeclarationAsDeclaredRules:
    """GroupDecisionRulesDeclaration が、集団の決定の規則の約束 (DeclaredGroupDecisionRules) として読めることを保証する。"""

    def test_rules_answer_the_declared_decision_and_selections(self) -> None:
        """追放の投票の規則を約束として読むと、宣言した決定・投票する人・選ばれうる人の選び方がそのまま返る。"""
        exile = GroupDecisionDeclaration(
            decision_id=GroupDecisionId("exile"),
            name=DisplayName("追放の投票"),
            abstain_allowed=True,
            reveals_ballots=False,
        )
        declaration = everyone_votes_on(exile)

        rules = as_declared_group_decision_rules(declaration)

        assert (rules.decision, rules.voters, rules.choices) == (exile, declaration.voters, declaration.choices)
