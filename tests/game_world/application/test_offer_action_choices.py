from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.being.contract import ActionChoice, ActionChoices, Candidate, FreeText, PersonInText, PickOne
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.offer_action_choices import OfferActionChoices, OfferActionChoicesCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_attempt import UsesBody
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.design_flaw.design_location import DesignLocation
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DisplayName,
    ObjectId,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_WORLD = WorldId("world")
_GEN, _SAYO = PersonId("gen"), PersonId("sayo")
_OFFICE = SpotId("company_office")
_HERE_IN_TEST = DesignLocation("test", "offer_action_choices", "nouns")


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


class _Office:
    """廃坑の山村 v2 を開き、ゲンとサヨが自分の名前で入って、鉱山会社の事務所へ移る。"""

    def __init__(self, design: WorldDesign, place: SpotId = _OFFICE) -> None:
        self._place = place
        store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="mine_village_v2",
            scenario_hash="mine_village_v2",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self.scope = CommandScope(store, CommittedEventsDistributor())
        self.design = design
        self.scope.run(self._move_to_office)

    def _move_to_office(self, session: WorldSession) -> None:
        office = self.design.nouns.spot_of(self._place)
        for person, name in ((_GEN, "ゲン"), (_SAYO, "サヨ")):
            session.people_register().name(person, DisplayName(name))
            session.aggregates().whereabouts().teleport(PersonBody(person), office, WorldTick(0))

    def keep_gen_busy(self) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates()
                .vitals(_GEN)
                .start_acting(UsesBody(), WorldTick(0) + Ticks(5), session.facts().rules().fatigue)
            )
        )

    def choices_of_gen(self) -> ActionChoices:
        return OfferActionChoices(self.scope, self.design)(OfferActionChoicesCommand(_GEN))


def _choice(choices: ActionChoices, name: str) -> ActionChoice:
    return next(choice for choice in choices.choices if choice.name == name)


def _labels(choice: ActionChoice) -> list[str | PersonInText]:
    [pick] = choice.values
    assert isinstance(pick, PickOne)
    return [candidate.label for candidate in pick.candidates]


def _candidate(choice: ActionChoice, label: str) -> Candidate:
    [pick] = choice.values
    assert isinstance(pick, PickOne)
    return next(candidate for candidate in pick.candidates if candidate.label == label)


class TestOfferActionChoices:
    """OfferActionChoices が、事務所にいるゲンに、D2226 の決まりどおりの行動の選択肢を渡すことを保証する。"""

    def test_every_choice_of_the_d2226_table_is_offered_in_a_fixed_order(self, mine_village: WorldDesign) -> None:
        """選べるものが無い行動も含めて、14 の選択肢がいつも同じ顔ぶれと順で並ぶ。"""
        choices = _Office(mine_village).choices_of_gen()

        assert [choice.name for choice in choices.choices] == [
            "travel_to",
            "set_sub_location",
            "explore",
            "interact",
            "wait",
            "speak",
            "use_item",
            "drop_item",
            "pickup_item",
            "give_item",
            "tend_to_player",
            "vote",
            "hold_item",
            "put_away_item",
        ]

    def test_gen_can_travel_to_the_well_the_smithy_and_the_south_adit_mouth(self, mine_village: WorldDesign) -> None:
        """「行く」の行き先の候補は、事務所から道の通じている井戸・鍛冶場・南の横坑口。"""
        choices = _Office(mine_village).choices_of_gen()

        assert sorted(_labels(_choice(choices, "travel_to"))) == sorted(["井戸", "鍛冶場", "南の横坑口"])

    def test_gen_can_whisper_to_sayo_shown_as_a_person_not_as_a_name(self, mine_village: WorldDesign) -> None:
        """「話す」は、ふつうの声・叫ぶ・ささやくが並び、ささやく相手の候補のサヨは名前の文字ではなく人の印で渡る。サヨを選んだら、中身を自由に書く。"""
        speak = _choice(_Office(mine_village).choices_of_gen(), "speak")

        [to] = _candidate(speak, "ささやく").values
        assert isinstance(to, PickOne)
        [sayo] = to.candidates

        assert _labels(speak) == ["ふつうの声で話す", "叫ぶ", "ささやく"]
        assert isinstance(sayo.label, PersonInText)
        assert sayo.label.visible_name == "サヨ"
        assert sayo.values == (FreeText(name="content", label="中身"),)

    def test_gen_can_open_the_safe_by_writing_a_code(self, mine_village: WorldDesign) -> None:
        """「操作する」の相手の候補に金庫があり、その下に「番号を合わせて金庫を開ける」と、自由に書く番号 (code) が続く。"""
        interact = _choice(_Office(mine_village).choices_of_gen(), "interact")

        [how] = _candidate(interact, "金庫").values
        assert isinstance(how, PickOne)
        [open_safe] = how.candidates

        assert open_safe.label == "番号を合わせて金庫を開ける"
        assert open_safe.values == (FreeText(name="code", label="code", writes="金庫の番号"),)

    def test_three_bottles_of_lamp_oil_are_one_candidate_with_a_count(self, mine_village: WorldDesign) -> None:
        """「置く」の品物の候補で、3 つ持っているカンテラの油は、数 3 を添えた 1 つの候補になる。"""
        drop = _choice(_Office(mine_village).choices_of_gen(), "drop_item")

        assert _candidate(drop, "カンテラの油").count == 3

    def test_busy_gen_can_only_speak_and_sees_why_the_rest_is_unavailable(self, mine_village: WorldDesign) -> None:
        """行っているあいだのゲンは、選べる選択肢が「話す」だけで、行き先の井戸は候補から外れ、理由つきの「いまはできない」に並ぶ。"""
        office = _Office(mine_village)
        office.keep_gen_busy()

        choices = office.choices_of_gen()
        travel = _choice(choices, "travel_to")

        assert [choice.name for choice in choices.choices if choice.can_be_chosen()] == ["speak"]
        assert _labels(travel) == []
        assert ("井戸",) in [unavailable.picked for unavailable in travel.unavailable]


def test_object_operations_refused_by_common_rules_stay_in_the_choices(mine_village: WorldDesign) -> None:
    """行っているあいだのゲンの金庫や事務机への操作は、「操作する」の「いまはできない」に残る。物の状態で断られたのではないので、場面の物の行には出さないため。"""
    office = _Office(mine_village)
    office.keep_gen_busy()

    interact = _choice(office.choices_of_gen(), "interact")

    assert {"金庫", "事務机"} <= {unavailable.picked[0] for unavailable in interact.unavailable}


def test_closed_gate_offers_opening_it_and_hides_closing_it(mine_village: WorldDesign) -> None:
    """閉じている北の坑道の水門は、「水門を開ける」だけを選べ、「水門を閉じる」は選べる候補にも「いまはできない」にも出ない。伏せる印のある操作は、条件を満たさないあいだ存在ごと伏せるため (古い run と同じ)。"""
    tunnel = _Office(mine_village, SpotId("north_tunnel"))

    interact = _choice(tunnel.choices_of_gen(), "interact")

    [how] = _candidate(interact, "北の坑道の水門").values
    assert isinstance(how, PickOne)
    hows = [str(candidate.label) for candidate in how.candidates]
    assert hows == ["水門を開ける"]
    assert all("水門を閉じる" not in str(unavailable.picked) for unavailable in interact.unavailable)


def test_busy_gen_still_does_not_see_closing_the_closed_gate(mine_village: WorldDesign) -> None:
    """行っているあいだのゲンにも、閉じている水門の「水門を閉じる」は「いまはできない」に出ない。伏せる印のある操作は、共通の決まりで断られるより先に、条件を満たさないことで伏せるため。"""
    tunnel = _Office(mine_village, SpotId("north_tunnel"))
    tunnel.keep_gen_busy()

    interact = _choice(tunnel.choices_of_gen(), "interact")

    picked = [str(unavailable.picked) for unavailable in interact.unavailable]
    assert any("水門を開ける" in p for p in picked)
    assert not any("水門を閉じる" in p for p in picked)


class TestOperationsNotPossibleNow:
    """物の状態が理由でいまできない操作が、行動の候補の「いまできない」に、対象と操作の道筋と理由つきで渡ることを保証する。"""

    def test_empty_bucket_puts_drawing_water_among_the_unavailable(self, mine_village: WorldDesign) -> None:
        """釣瓶の水が尽きると、interact のいまできないに、道筋 (井戸の釣瓶, 水を汲む) と、釣瓶が空のまま上がってきた理由が並ぶ。"""
        well = _Office(mine_village, SpotId("well"))
        water = mine_village.nouns.object_state_key("well_bucket", "water", _HERE_IN_TEST)
        well.scope.run(
            lambda session: (
                session.aggregates()
                .object_state(ObjectId("well_bucket"))
                .take_from_stock(water, Count(4), WorldTick(0))
            )
        )

        unavailable = _choice(well.choices_of_gen(), "interact").unavailable

        assert (("井戸の釣瓶", "水を汲む"), "釣瓶は空のまま上がってきた。底の水が溜まるのを待つしかない。") in [
            (tuple(u.picked), u.reason) for u in unavailable
        ]

    def test_closed_gate_hides_closing_it(self, mine_village: WorldDesign) -> None:
        """閉じている北の坑道の水門の「水門を閉じる」は、いまできないにも出ない。伏せる印のある操作は、条件を満たさないあいだ存在ごと伏せるため。"""
        unavailable = _choice(_Office(mine_village, SpotId("north_tunnel")).choices_of_gen(), "interact").unavailable

        assert all("水門を閉じる" not in u.picked for u in unavailable)
