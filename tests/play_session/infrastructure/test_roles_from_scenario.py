from __future__ import annotations

from pathlib import Path

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.play_session.infrastructure.roles_from_scenario import casting_by_person_name, roles_from_scenario

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"


class TestRolesFromScenario:
    """roles_from_scenario が、シナリオの登場人物ごとに、人柄と立場と目的を同じ人のものでそろえた役にすることを保証する。"""

    def test_gens_role_carries_his_own_persona_facts_and_objective(self) -> None:
        """ゲンの役は、名前「ゲン」・ゲンの人柄の欄・ゲンの立場 (金庫の番号 1907) と目的を持つ。"""
        scenario = load_scenario(_MINE_VILLAGE)

        gen = {role.person: role for role in roles_from_scenario(scenario)}[PersonId("gen")]

        assert (gen.being_name, gen.persona_fields["first_person"]) == ("ゲン", "俺")
        assert "1907" in gen.known_facts.text
        assert gen.objective.text == "サヨと二人そろって、坑道の奥の昇降機で外へ出る。"

    def test_every_character_gets_a_role(self) -> None:
        """廃坑の山村 v2 の 4 人 (ゲン・サヨ・ハル・ミオ) がそれぞれ役になる。"""
        scenario = load_scenario(_MINE_VILLAGE)

        people = {role.person.value for role in roles_from_scenario(scenario)}

        assert people == {"gen", "sayo", "haru", "mio"}


class TestCastingByPersonName:
    """casting_by_person_name が、既定の配役として、登場人物の名前と同じ BeingId を当てることを保証する。"""

    def test_each_person_is_played_by_the_being_of_the_same_name(self) -> None:
        """廃坑の山村 v2 の 4 人に、gen → BeingId("gen") のように同じ名前の Being を当てる。"""
        scenario = load_scenario(_MINE_VILLAGE)

        casting = casting_by_person_name(scenario)

        assert casting == {PersonId(name): BeingId(name) for name in ("gen", "sayo", "haru", "mio")}
