from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Perception
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerceptionCommand
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.perception.people_present import WhoeverIsThere
from ai_rpg_world.game_world.domain.perception.perception_cause import TimePassed
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from tests.play_session.mine_village_session import MineVillageSession


def _door_breaks_at(spot: SpotId, *, by: PersonId | None = None) -> SightStimulus:
    actor = {} if by is None else {"actor": by}
    clear = "扉が壊れた" if by is None else "{actor}が扉を壊した"
    return SightStimulus(
        where=spot,
        witness=SightTexts(
            clear=TextWithUnassignedPeople(clear).about(actor),
            dim=TextWithUnassignedPeople("何かが崩れた").about({}),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=() if by is None else (by,),
        salience=Notable(),
        always_delivered=False,
        at=WorldTick(0),
        present=WhoeverIsThere(),
    )


class TestHandObservationToBeing:
    """HandObservationToBeing が、世界の観測の出口から届いた観測を、その登場人物を動かす Being の短期記憶に入れることを保証する。"""

    def test_door_breaking_reaches_only_gen_who_was_there(self) -> None:
        """南の横坑口で扉が壊れると、そこにいたゲンの短期記憶に観測が 1 件入り、北の坑道口にいたハルには入らない。"""
        session = MineVillageSession().started()

        session.deliver_perception(
            DeliverPerceptionCommand(
                cause=TimePassed(), from_actions=(_door_breaks_at(SpotId("south_adit_mouth")),), from_states=()
            )
        )

        gens = session.short_term_memories.get(BeingId("gen")).experiences
        assert [type(e) for e in gens] == [Perception]
        assert session.short_term_memories.get(BeingId("haru")).experiences == ()

    def test_people_in_the_observation_are_named_before_entering_memory(self) -> None:
        """南の横坑口でサヨが扉を壊すと、ゲンの短期記憶には、人の穴を、世界に名乗ったサヨの名前で埋めた「サヨが扉を壊した」で入る。"""
        session = MineVillageSession().started()

        session.deliver_perception(
            DeliverPerceptionCommand(
                cause=TimePassed(),
                from_actions=(_door_breaks_at(SpotId("south_adit_mouth"), by=PersonId("sayo")),),
                from_states=(),
            )
        )

        [perceived] = session.short_term_memories.get(BeingId("gen")).experiences
        assert isinstance(perceived, Perception)
        assert perceived.observation.body == "サヨが扉を壊した"
