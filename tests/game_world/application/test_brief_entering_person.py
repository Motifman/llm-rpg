from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson, BriefEnteringPersonCommand
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

    def test_orientation_has_introduction_premises_and_what_gen_knows(self, scenario: LoadedScenario) -> None:
        """ゲンの案内には「この世界について」「この世界の前提」「あなたが知っていること」がこの順に並び、知っていることに金庫の番号 1907 がある。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        descriptions = tuple(briefing.orientation.descriptions)
        assert [d.heading for d in descriptions] == ["この世界について", "この世界の前提", "あなたが知っていること"]
        assert descriptions[0].text.startswith("冬が近い山あいの廃村。")
        assert "昇降機は一度しか動かない。" in descriptions[1].text
        assert "1907" in descriptions[2].text

    def test_imposed_goal_is_only_gens_objective(self, scenario: LoadedScenario) -> None:
        """ゲンに課す目的は、ゲンの objective「サヨと二人そろって、坑道の奥の昇降機で外へ出る。」だけになる。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        assert briefing.imposed_goal == "サヨと二人そろって、坑道の奥の昇降機で外へ出る。"

    def test_gen_knows_only_sayo_at_start(self, scenario: LoadedScenario) -> None:
        """ゲンが最初から知っている人はサヨだけで、ハルとミオは入らない。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        assert briefing.known_people == (PersonId("sayo"),)
