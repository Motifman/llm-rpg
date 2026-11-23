from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.built_in_attempts import TravelAttempt
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.own_action_completion import OwnActionCompletion
from ai_rpg_world.game_world.domain.perception.people_present import PeopleWhoWereThere
from ai_rpg_world.game_world.domain.perception.sight_stimulus import SightStimulus
from ai_rpg_world.game_world.domain.perception.sound_stimulus import SoundStimulus
from ai_rpg_world.game_world.domain.value_object import PassageId, PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import CameThrough, PersonBody
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from tests.game_world.support.world_design_for_tests import compose_world, nouns, passage, spot

_MINE_VILLAGE = Path(__file__).parents[4] / "data" / "scenarios" / "mine_village_v2.yaml"
_GEN = PersonId("gen")


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


class TestArrivalStimuli:
    """WorldDesign.arrival_stimuli が、着いた本人には自分の行動の結果だけを、ほかの人には目撃と足音を作ることを保証する。"""

    def test_sight_and_footsteps_are_withheld_from_the_arriver(self, mine_village: WorldDesign) -> None:
        """山村 v2 でゲンが南の横坑口から南の横坑の奥に着くと、目撃の文も足音も、ゲン自身には届けない印を持つ。"""
        stimuli = mine_village.arrival_stimuli(
            SpotId("south_adit_end"),
            PersonBody(_GEN),
            CameThrough(SpotId("south_adit_mouth"), PassageId("south_adit")),
            WorldTick(1),
        )

        others = [s for s in stimuli if isinstance(s, (SightStimulus, SoundStimulus))]
        assert {type(s) for s in others} == {SightStimulus, SoundStimulus}
        assert all(s.withheld_from == frozenset({_GEN}) for s in others)

    def test_others_see_the_old_runs_line_with_the_passage(self, mine_village: WorldDesign) -> None:
        """山村 v2 でゲンが南の横坑口から横坑を通って南の横坑の奥に着くと、ほかの人の目撃の文は古い run と同じ「{actor}が「南の横坑口」から〈横坑〉を通って南の横坑の奥にやってきた。」になる。"""
        [sight] = [
            s
            for s in mine_village.arrival_stimuli(
                SpotId("south_adit_end"),
                PersonBody(_GEN),
                CameThrough(SpotId("south_adit_mouth"), PassageId("south_adit")),
                WorldTick(1),
            )
            if isinstance(s, SightStimulus)
        ]

        assert (
            sight.witness.clear.template.template
            == "{actor}が「南の横坑口」から〈横坑〉を通って南の横坑の奥にやってきた。"
        )

    def test_arriver_gets_the_old_runs_arrival_line(self, mine_village: WorldDesign) -> None:
        """着いた本人には、古い run と同じ要約「「南の横坑の奥」に着いた」と結果の文が、行く (travel_to) の続きとして届く。"""
        [completion] = [
            s
            for s in mine_village.arrival_stimuli(
                SpotId("south_adit_end"),
                PersonBody(_GEN),
                CameThrough(SpotId("south_adit_mouth"), PassageId("south_adit")),
                WorldTick(1),
            )
            if isinstance(s, OwnActionCompletion)
        ]

        assert (completion.summary.template.template, completion.text.template.template, completion.tool) == (
            "「南の横坑の奥」に着いた",
            "「南の横坑の奥」に到着した。ここから次の行動を選べる。",
            "travel_to",
        )


class TestTravelTexts:
    """TravelAttempt の要約と結果の文が、出発した場所を行う直前の居場所から書くことを保証する。"""

    def test_origin_is_filled_into_the_result_text_too(self) -> None:
        """結果の文に {origin} を書いた世界でも、行う直前にいた広場の名前が入る。"""
        design = compose_world(nouns(spots=(spot("plaza"), spot("well"))))
        situation = ActorSituation(at_spot=SpotId("plaza"), actor_as=PersonBody(_GEN), item_specs={})

        done = TravelAttempt(_GEN, spot("well")).done_text_in(design, situation)

        assert done.template.template == "travelできた。 well plaza"


class TestDepartureWitness:
    """去っていく人の目撃の文が、古い run と同じく、通ってゆく通路の名前と行き先を書くことを保証する。"""

    def test_gen_leaving_through_the_adit_is_seen_like_the_old_run(self, mine_village: WorldDesign) -> None:
        """山村 v2 でゲンが南の横坑口から南の横坑の奥へ向かうと、目撃の文は「{actor}が〈横坑〉を抜けて「南の横坑の奥」へ去っていった。」になる。"""
        situation = ActorSituation(at_spot=SpotId("south_adit_mouth"), actor_as=PersonBody(_GEN), item_specs={})
        attempt = TravelAttempt(_GEN, mine_village.nouns.spot_of(SpotId("south_adit_end")))

        [sight] = [
            s
            for s in attempt.witnessed_in(mine_village, situation).stimuli_at(
                SpotId("south_adit_mouth"), PersonBody(_GEN), PeopleWhoWereThere(), WorldTick(1)
            )
            if isinstance(s, SightStimulus)
        ]

        assert sight.witness.clear.template.template == "{actor}が〈横坑〉を抜けて「南の横坑の奥」へ去っていった。"

    def test_first_declared_of_two_passages_names_the_way(self) -> None:
        """広場から井戸へ通路が 2 本あると、去っていく文には、古い run と同じく宣言の順で先の通路の名前を使う。"""
        design = compose_world(
            nouns(
                spots=(spot("plaza"), spot("well")),
                passages=(passage("upper", ("plaza", "well")), passage("lower", ("plaza", "well"))),
            )
        )

        assert design.nouns.first_passage_between(SpotId("plaza"), SpotId("well")).passage_id == PassageId("upper")
