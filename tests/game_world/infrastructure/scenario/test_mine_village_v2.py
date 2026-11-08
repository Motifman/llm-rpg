from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.person_conditions import IsInSectionCondition
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import MembershipVisibility
from ai_rpg_world.game_world.domain.declaration.verb import HappeningDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import ForEveryoneEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import SetOutcomeEffect
from ai_rpg_world.game_world.domain.value_object import Capacity, ObjectId, PersonId, SpotId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario

_MINE_VILLAGE = Path(__file__).parents[4] / "data" / "scenarios" / "mine_village_v2.yaml"


@pytest.fixture(scope="module")
def mine_village() -> LoadedScenario:
    return load_scenario(_MINE_VILLAGE)


def _happening(loaded: LoadedScenario, name: str) -> HappeningDeclaration:
    (happening,) = (h for h in loaded.design.happenings() if h.happening_id.value == name)
    return happening


def _outcome_by_cage(step: object) -> tuple[str, bool]:
    assert isinstance(step, ForEveryoneEffect)
    assert isinstance(step.effect, SetOutcomeEffect)
    where = step.people.where
    assert isinstance(where, AllOfCondition)
    in_cage = [child for child in where.children if isinstance(child, IsInSectionCondition)]
    out_of_cage = [
        child
        for child in where.children
        if isinstance(child, NotCondition) and isinstance(child.child, IsInSectionCondition)
    ]
    (cage_condition,) = in_cage or [condition.child for condition in out_of_cage]  # type: ignore[attr-defined]
    assert cage_condition.section.section_id.value == "cage"
    return step.effect.outcome.outcome_id.value, bool(in_cage)


class TestMineVillageLoads:
    """廃坑の山村の新しい形式 (mine_village_v2.yaml) が、読み込みにそのまま通ることを保証する。"""

    def test_loads_into_world_design_without_flaws_or_warnings(self, mine_village: LoadedScenario) -> None:
        """読み込むと DesignFlaw を出さずに WorldDesign になり、書き忘れた知覚の文を埋めた DesignWarning も残らない。"""
        assert mine_village.warnings == ()

    def test_two_pairs_start_at_their_own_entrances(self, mine_village: LoadedScenario) -> None:
        """ハルとミオは北の竪坑口、ゲンとサヨは南の横坑口から始まり、4 人とも Being に渡す人柄を持つ。"""
        starts = {person.person: person.spawn_spot.spot_id for person in mine_village.design.initial_world().people}

        assert starts == {
            PersonId("haru"): SpotId("north_shaft_head"),
            PersonId("mio"): SpotId("north_shaft_head"),
            PersonId("gen"): SpotId("south_adit_mouth"),
            PersonId("sayo"): SpotId("south_adit_mouth"),
        }
        assert set(mine_village.beings) == set(starts)


class TestLiftCage:
    """昇降機の籠が、乗った印の品物や人の属性ではなく、乗り場の区画として宣言されていることを保証する。"""

    def test_cage_holds_three_and_only_it_reaches_the_panel(self, mine_village: LoadedScenario) -> None:
        """乗り場の区画は籠 1 つで定員 3、操作盤は籠の中からしか届かず、昇降機を動かす操作は操作盤にしか無い。"""
        design = mine_village.design
        (cage,) = design.nouns.sections_at(SpotId("lift_landing"))

        assert (cage.section_id.value, cage.capacity, cage.reachable_objects) == (
            "cage",
            Capacity(3),
            (ObjectId("lift_panel"),),
        )
        assert [i.interaction_id.value for i in design.interactions_on_object(ObjectId("lift_panel"))] == ["start_lift"]
        assert design.interactions_on_object(ObjectId("lift")) == ()

    def test_lift_leaving_rescues_the_cage_and_strands_the_rest(self, mine_village: LoadedScenario) -> None:
        """籠が上がった旗が立つと 1 回だけ起きる出来事が、籠の中の人を救出、籠の外の人を取り残されたにする。"""
        lift_leaves = _happening(mine_village, "lift_leaves")

        assert lift_leaves.once is True
        assert isinstance(lift_leaves.condition, FlagIsRaisedCondition)
        assert lift_leaves.condition.flag.flag_id.value == "lift_departed"
        assert isinstance(lift_leaves.effect, SequenceEffect)
        assert [_outcome_by_cage(step) for step in lift_leaves.effect.steps] == [
            ("rescued", True),
            ("stranded", False),
        ]


class TestTeams:
    """2 組の所属が、本人にだけ分かる分け方として宣言されていることを保証する。"""

    def test_each_pair_belongs_to_its_own_self_only_team(self, mine_village: LoadedScenario) -> None:
        """所属の分け方は SELF_ONLY で変わらず、北の 2 人はチーム北、南の 2 人はチーム南に入って始まる。"""
        people = mine_village.design.initial_world().people
        groups = {person.person: [group.group_id.value for group in person.groups] for person in people}
        (grouping,) = {group.grouping for person in people for group in person.groups}

        assert (grouping.visibility, grouping.changes) == (MembershipVisibility.SELF_ONLY, False)
        assert groups == {
            PersonId("haru"): ["team_north"],
            PersonId("mio"): ["team_north"],
            PersonId("gen"): ["team_south"],
            PersonId("sayo"): ["team_south"],
        }
