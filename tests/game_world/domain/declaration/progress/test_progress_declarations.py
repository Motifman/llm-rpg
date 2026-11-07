from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.progress import (
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, FlagId, GroupDecisionId, OutcomeId


class TestFlagDeclarationAsKey:
    """FlagDeclaration が、条件の見る旗の集合 (waits_for_flags など) に入れられることを保証する。"""

    def test_declarations_with_same_fields_are_equal_and_hash_alike(self) -> None:
        """同じ欄を持つ 2 つの FlagDeclaration は等しく、集合では 1 つにまとまる。"""
        first = FlagDeclaration(
            flag_id=FlagId("power_on"), meaning=DescriptionText("電源が入った"), initially_raised=False
        )
        second = FlagDeclaration(
            flag_id=FlagId("power_on"), meaning=DescriptionText("電源が入った"), initially_raised=False
        )

        assert first == second
        assert len({first, second}) == 1


class TestGroupDecisionDeclarationAsKey:
    """GroupDecisionDeclaration が、集団の決定の記録のキーとして使えることを保証する。"""

    def test_declarations_with_same_fields_are_equal_and_hash_alike(self) -> None:
        """同じ欄を持つ 2 つの GroupDecisionDeclaration は等しく、集合では 1 つにまとまる。"""
        first = GroupDecisionDeclaration(
            decision_id=GroupDecisionId("exile_vote"),
            name=DisplayName("追放の投票"),
            abstain_allowed=True,
            reveals_ballots=False,
        )
        second = GroupDecisionDeclaration(
            decision_id=GroupDecisionId("exile_vote"),
            name=DisplayName("追放の投票"),
            abstain_allowed=True,
            reveals_ballots=False,
        )

        assert first == second
        assert len({first, second}) == 1


class TestOutcomeAnnouncement:
    """OutcomeDeclaration.announcement が、結末を迎えた人を割り当てる前の文として持たれることを保証する。"""

    def test_keeps_person_placeholders_unassigned(self) -> None:
        """announcement の人のプレースホルダーは、宣言の時点では割り当てられずに残る。"""
        outcome = OutcomeDeclaration(
            outcome_id=OutcomeId("rescued"),
            name=DisplayName("救出"),
            announcement=TextWithUnassignedPeople("{person}は昇降機で外へ出た。"),
        )

        assert outcome.announcement.placeholders() == frozenset({"person"})
