from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson, BriefEnteringPersonCommand
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_GEN = PersonId("gen")


@pytest.fixture(scope="module")
def scenario() -> LoadedScenario:
    return load_scenario(_MINE_VILLAGE)


def _brief_gen(scenario: LoadedScenario) -> BriefEnteringPersonCommand:
    briefing = scenario.briefings[_GEN]
    return BriefEnteringPersonCommand(person=_GEN, known_facts=briefing.known_facts, objective=briefing.objective)


class TestBriefEnteringPerson:
    """BriefEnteringPerson が、廃坑の山村 v2 に入るゲンに、案内・課す目的・最初から知っている人を返すことを保証する。"""

    def test_orientation_has_introduction_premises_map_and_what_gen_knows(self, scenario: LoadedScenario) -> None:
        """ゲンの案内には「この世界について」「この世界の前提」「この場所の造り」「あなたが知っていること」がこの順に並び、知っていることに金庫の番号 1907 がある。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        descriptions = tuple(briefing.orientation.descriptions)
        introduction, premises, _, known_facts = (d.text for d in descriptions)
        assert [d.heading for d in descriptions] == [
            "この世界について",
            "この世界の前提",
            "この場所の造り",
            "あなたが知っていること",
        ]
        assert isinstance(introduction, str) and introduction.startswith("冬が近い山あいの廃村。")
        assert isinstance(premises, str) and "昇降機は一度しか動かない。" in premises
        assert isinstance(known_facts, str) and "1907" in known_facts

    def test_map_lists_every_place_with_its_neighbours_in_minutes(self, scenario: LoadedScenario) -> None:
        """「この場所の造り」は 21 の場所を 1 行ずつ載せ、北の竪坑口の行は、1 tick を 30 分として近い順に行き先を並べる。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        world_map = tuple(briefing.orientation.descriptions)[2].text
        assert isinstance(world_map, str)
        lines = world_map.splitlines()
        assert len(lines) == 21
        assert lines[0] == "  北の竪坑口 (明るい) → 北の竪坑の底 まで 30 分 / 集会所 まで 30 分 / 雪の峠道 まで 60 分"
        assert "  昇降機の乗り場 (暗い) → 下層の近道 まで 30 分 / 古い支柱の通路 まで 60 分" in lines

    def test_imposed_goal_is_only_gens_objective(self, scenario: LoadedScenario) -> None:
        """ゲンに課す目的は、ゲンの objective「サヨと二人そろって、坑道の奥の昇降機で外へ出る。」だけになる。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        assert briefing.imposed_goal == "サヨと二人そろって、坑道の奥の昇降機で外へ出る。"

    def test_gen_knows_only_sayo_at_start(self, scenario: LoadedScenario) -> None:
        """ゲンが最初から知っている人はサヨだけで、ハルとミオは入らない。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        assert briefing.known_people == (PersonId("sayo"),)

    def test_undeclared_person_is_refused(self, scenario: LoadedScenario) -> None:
        """シナリオに無い人 (kuro) を渡すと UndeclaredNounException を投げる。"""
        briefing = scenario.briefings[_GEN]
        command = BriefEnteringPersonCommand(
            person=PersonId("kuro"), known_facts=briefing.known_facts, objective=briefing.objective
        )

        with pytest.raises(UndeclaredNounException):
            BriefEnteringPerson(scenario.design)(command)
