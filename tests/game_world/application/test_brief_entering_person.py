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
    return BriefEnteringPersonCommand(person=_GEN, objective=briefing.objective)


class TestBriefEnteringPerson:
    """BriefEnteringPerson が、廃坑の山村 v2 に入るゲンに、案内・課す目的・最初から知っている人を返すことを保証する。"""

    def test_orientation_is_the_world_premises_like_the_old_run(self, scenario: LoadedScenario) -> None:
        """ゲンの案内の 1 つ目は「世界の前提」で、古い run と同じく題名と概要の 2 段落、空行、地図の見出しの順に始まり、知っていること (金庫の番号) は入らない。知っていることは Being が【ペルソナ】に出す (D2267)。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        premises, _ = tuple(briefing.orientation.descriptions)
        assert premises.heading == "世界の前提"
        assert isinstance(premises.text, str) and premises.text.splitlines()[:6] == [
            "- 舞台のタイトル: 廃坑の山村",
            "- 概要: 冬が近い山あいの廃村。外へ出る峠道は雪で閉ざされた。外へ出る手段は、村の下に広がる古い坑道の奥にある"
            "昇降機だけだという。昇降機は一度上がったら二度と下りてこず、籠には三人しか乗れないと聞いている。",
            "",
            "坑道の中は光が無いと何も見えない。古い坑道には、まだ誰も知らない仕掛けが残っているかもしれない。",
            "",
            "【この場所の造り】",
        ]
        assert "1907" not in premises.text

    def test_world_rules_follow_the_premises_like_the_old_run(self, scenario: LoadedScenario) -> None:
        """ゲンの案内の 2 つ目は「この世界の決まり」で、古い run と同じく、ラベル・一言 (say_inline)・勝利条件の行がこの順に並ぶ。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        _, rules = tuple(briefing.orientation.descriptions)

        assert rules.heading == "この世界の決まり"
        assert isinstance(rules.text, str)
        lines = rules.text.splitlines()
        assert len(lines) == 3
        assert lines[0].startswith("- ラベル（接続先・オブジェクト・相手プレイヤー等）は")
        assert lines[1].startswith("- `say_inline` を持つツールでは")
        assert lines[2].startswith("- **このシナリオの勝利条件")

    def test_mine_village_has_no_deadline_line(self, scenario: LoadedScenario) -> None:
        """山村 v2 は時間で終わらないので、世界の前提に「行動の制限」の行は出ない。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        premises, _ = tuple(briefing.orientation.descriptions)
        assert isinstance(premises.text, str) and "行動の制限" not in premises.text

    def test_map_lists_every_place_with_its_neighbours_in_minutes(self, scenario: LoadedScenario) -> None:
        """世界の前提の中の「【この場所の造り】」は 21 の場所を 1 行ずつ載せ、北の竪坑口の行は、1 tick を 30 分として近い順に行き先を並べる。"""
        briefing = BriefEnteringPerson(scenario.design)(_brief_gen(scenario))

        premises, _ = tuple(briefing.orientation.descriptions)
        assert isinstance(premises.text, str)
        lines = premises.text.split("【この場所の造り】\n")[1].splitlines()
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
        command = BriefEnteringPersonCommand(person=PersonId("kuro"), objective=briefing.objective)

        with pytest.raises(UndeclaredNounException):
            BriefEnteringPerson(scenario.design)(command)
