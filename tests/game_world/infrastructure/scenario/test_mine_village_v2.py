from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import LookingAround
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.object_state_conditions import ObjectValueIsCondition
from ai_rpg_world.game_world.domain.condition.person_conditions import (
    IsAliveCondition,
    IsAtSpotCondition,
    IsDownCondition,
    IsInSectionCondition,
)
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import MembershipVisibility
from ai_rpg_world.game_world.domain.declaration.object_and_item import Lasts, ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item.state_value import ChoiceName, ChoiceValue
from ai_rpg_world.game_world.domain.declaration.verb import HappeningDeclaration, ObjectLooksDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.effect.combined_effects import ConditionalEffect, ForEveryoneEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.flag_effects import LowerFlagEffect
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import SetOutcomeEffect
from ai_rpg_world.game_world.domain.objects_and_items.object_state import ObjectState
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Count,
    DescriptionText,
    ObjectId,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario
from tests.game_world.support.world_in_memory import world_in_memory

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
    cage_conditions: list[tuple[IsInSectionCondition, bool]] = []
    for child in where.children:
        if isinstance(child, IsInSectionCondition):
            cage_conditions.append((child, True))
        elif isinstance(child, NotCondition) and isinstance(child.child, IsInSectionCondition):
            cage_conditions.append((child.child, False))
    ((cage_condition, inside),) = cage_conditions
    assert cage_condition.section.section_id.value == "cage"
    return step.effect.outcome.outcome_id.value, inside


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


class TestBeastHappenings:
    """モンスターの代わりの獣の出来事が、痛手を当てられる人だけを襲うことを保証する。"""

    @pytest.mark.parametrize(
        ("happening", "spot"),
        [
            ("beast_north_attacks", "north_tunnel"),
            ("beast_south_attacks", "south_tunnel"),
            ("beast_deep_attacks", "mid_junction"),
        ],
    )
    def test_beast_attacks_only_standing_people_at_its_spot(
        self, mine_village: LoadedScenario, happening: str, spot: str
    ) -> None:
        """獣が襲うのは出る場所にいて倒れても死んでもいない人だけで、倒れた人に痛手を当てて出来事ごと断られることが無い。"""
        attacks = _happening(mine_village, happening)
        assert isinstance(attacks.effect, ForEveryoneEffect)
        where = attacks.effect.people.where
        assert isinstance(where, AllOfCondition)

        kinds = {type(child) for child in where.children}
        at_spot = [child for child in where.children if isinstance(child, IsAtSpotCondition)]
        not_down = [
            child
            for child in where.children
            if isinstance(child, NotCondition) and isinstance(child.child, IsDownCondition)
        ]

        assert [condition.spot.spot_id for condition in at_spot] == [SpotId(spot)]
        assert IsAliveCondition in kinds
        assert len(not_down) == 1


class TestPumpDrains:
    """排水ポンプが、弁の先の水門が開いているあいだは水を引かないことを保証する。"""

    def test_pump_lowers_a_flood_only_while_its_gate_is_closed(self, mine_village: LoadedScenario) -> None:
        """弁の一・二・三はそれぞれ南の出入り口・下層の近道・北の出入り口の水を、水門 A・C・B が閉じているときだけ引かせる。"""
        pump_drains = _happening(mine_village, "pump_drains")
        assert isinstance(pump_drains.effect, SequenceEffect)

        drains: dict[str, tuple[str, str]] = {}
        for step in pump_drains.effect.steps:
            if not isinstance(step, ConditionalEffect):
                continue
            assert isinstance(step.condition, AllOfCondition)
            assert isinstance(step.then, LowerFlagEffect)
            (mark,) = [c for c in step.condition.children if isinstance(c, ObjectValueIsCondition)]
            (gate,) = [
                c.child
                for c in step.condition.children
                if isinstance(c, NotCondition) and isinstance(c.child, FlagIsRaisedCondition)
            ]
            assert isinstance(gate, FlagIsRaisedCondition)
            assert isinstance(mark.value, ChoiceValue)
            drains[mark.value.choice.value] = (gate.flag.flag_id.value, step.then.flag.flag_id.value)

        assert drains == {
            "one": ("gate_a_open", "flooded_south_entry"),
            "two": ("gate_c_open", "flooded_shortcut"),
            "three": ("gate_b_open", "flooded_north_entry"),
        }


_START = WorldTick(0)


def _object(loaded: LoadedScenario, name: str) -> ObjectDeclaration:
    return loaded.design.nouns.object(name, DesignLocation("object", name, ""))


def _looks(loaded: LoadedScenario, name: str) -> ObjectLooksDeclaration:
    return loaded.design.looks_of(ObjectId(name))


def _world_with(loaded: LoadedScenario, *raised: str, states: tuple[ObjectState, ...] = ()) -> WorldSession:
    nouns = loaded.design.nouns
    a_world = world_in_memory(
        world=WorldId("mine_village"),
        spots=nouns.all_spots(),
        objects=tuple(nouns.object_of(state.object_id) for state in states),
        object_states=states,
    )
    for name in raised:
        a_world.aggregates().flags().raise_flag(
            loaded.design.nouns.flag(name, DesignLocation("flag", name, "")), LookingAround(_START)
        )
    return a_world


class TestObjectLooks:
    """廃坑の山村の物が、v1 の state_display と同じ文で、いまの状態ごとの見え方を持つことを保証する。"""

    @pytest.mark.parametrize(
        ("name", "flag", "raised_text", "lowered_text"),
        [
            ("office_safe", "safe_opened", "扉が開いていて、中は空だ", "扉は固く閉じている"),
            ("gate_a", "gate_a_open", "開いていて、水の流れる音がする", "閉じている"),
            ("gate_b", "gate_b_open", "開いていて、水の流れる音がする", "閉じている"),
            ("gate_c", "gate_c_open", "開いていて、水の流れる音がする", "閉じている"),
            ("old_timber", "timber_felled", "倒れて、崩れた岩が道を埋めている", "傾きながらも天井を支えている"),
            ("lift", "lift_departed", "籠はもう上がってしまった", "籠は乗り場に止まっている"),
        ],
    )
    def test_look_follows_the_world_flag(
        self, mine_village: LoadedScenario, name: str, flag: str, raised_text: str, lowered_text: str
    ) -> None:
        """旗が立っているときと立っていないときで、物の見え方が v1 の 2 つの文に分かれる。"""
        looks = _looks(mine_village, name)

        raised = looks.look_now(_world_with(mine_village, flag).facts())
        lowered = looks.look_now(_world_with(mine_village).facts())

        assert (raised, lowered) == (DescriptionText(raised_text), DescriptionText(lowered_text))

    @pytest.mark.parametrize(
        ("fuel", "text"),
        [
            (0, "燃料計の針は空を指している"),
            *((n, f"燃料計の針は{n}つ目の目盛りを指している") for n in range(1, 8)),
        ],
    )
    def test_fuel_gauge_text_changes_with_each_amount(self, mine_village: LoadedScenario, fuel: int, text: str) -> None:
        """発電機の燃料が 0 から 7 のどれかのとき、燃料計の文はその量の目盛りを言う。"""
        generator = _object(mine_village, "generator")
        (fuel_key,) = generator.state_keys
        state = ObjectState.from_declaration(generator, _START)
        state.add_to_count(fuel_key, Count(fuel))

        look = _looks(mine_village, "generator").look_now(_world_with(mine_village, states=(state,)).facts())

        assert look == DescriptionText(text)

    @pytest.mark.parametrize(
        ("mark", "text"),
        [("one", "一の目盛りを指している"), ("two", "二の目盛りを指している"), ("three", "三の目盛りを指している")],
    )
    def test_valve_text_follows_its_mark(self, mine_village: LoadedScenario, mark: str, text: str) -> None:
        """切り替え弁の目盛りが一・二・三のどれかのとき、その目盛りを指している文になる。"""
        valve = _object(mine_village, "valve")
        (mark_key,) = valve.state_keys
        state = ObjectState.from_declaration(valve, _START)
        state.set(mark_key, ChoiceValue(ChoiceName(mark)), _START)

        look = _looks(mine_village, "valve").look_now(_world_with(mine_village, states=(state,)).facts())

        assert look == DescriptionText(text)


class TestLightsBurnOut:
    """カンテラの灯とたいまつが、決まった tick の一斉の出来事ではなく、品物ごとの持つ時間で燃え尽きることを保証する。"""

    @pytest.mark.parametrize(
        ("item_spec", "lasts"),
        [
            ("lamp_flame", Lasts(ticks=Ticks(16), ended_text=DescriptionText("カンテラの灯が燃え尽きた。"))),
            (
                "torch",
                Lasts(ticks=Ticks(24), ended_text=DescriptionText("火が燃え尽き、手もとには焦げた棒だけが残った。")),
            ),
        ],
    )
    def test_light_lasts_its_own_ticks_with_the_v1_text(
        self, mine_village: LoadedScenario, item_spec: str, lasts: Lasts
    ) -> None:
        """灯は 16 tick、たいまつは 24 tick の Lasts を持ち、燃え尽きた文は v1 の event_removal_message と同じになる。"""
        declared = mine_village.design.nouns.item_spec(item_spec, DesignLocation("item_spec", item_spec, "lasts"))

        assert declared.lasts == lasts

    def test_no_happening_burns_lights_out_all_at_once(self, mine_village: LoadedScenario) -> None:
        """燃え尽きの出来事 lamp_flames_burn_out と torches_burn_out は宣言に無い。"""
        names = {happening.happening_id.value for happening in mine_village.design.happenings()}

        assert names.isdisjoint({"lamp_flames_burn_out", "torches_burn_out"})
