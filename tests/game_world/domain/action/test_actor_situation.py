from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemHandOverAttempt, TravelAttempt
from ai_rpg_world.game_world.domain.action.delivery import Delivery
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, PersonId, SpotId, WorldId
from ai_rpg_world.game_world.domain.whereabouts import NotAtSpot, PersonBody, Route
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    item_spec,
    nouns,
    passage,
    spot,
)

_WORLD = WorldId("situation_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_ROPE = item_spec("rope")
_LAMP = item_spec("lamp")
_ROAD = passage("road", ("hall", "yard"))


def _opened_world() -> WorldSession:
    alice = replace(character("alice", "hall"), initial_items=(_ROPE.item_spec_id, _LAMP.item_spec_id))
    design = compose_world(
        nouns(
            spots=(spot("hall"), spot("yard")),
            passages=(_ROAD,),
            item_specs=(_ROPE, _LAMP),
            characters=(alice, character("bob", "hall")),
        )
    )
    store = SqliteWorldStore.create(
        ":memory:", world_id=_WORLD, scenario="s", scenario_hash="h", design=design, random=SeedableRandomSource(0)
    )
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    return store.session()


class TestActorSituationOf:
    """ActorSituation.of が、行う人のいた場所・姿と、試みが扱う品物の種類を、世界を変える前の状態から読むことを保証する。"""

    def test_actor_at_spot_is_read_with_spot_and_body(self) -> None:
        """場所にいる生きた人の試みは、その場所の SpotId と PersonBody を持ち、品物を扱わなければ品物は空。"""
        session = _opened_world()

        situation = ActorSituation.of(TravelAttempt(_ALICE, spot("yard")), session.facts())

        assert (situation.at_spot, situation.actor_as, dict(situation.item_specs)) == (
            SpotId("hall"),
            PersonBody(_ALICE),
            {},
        )

    def test_travelling_actor_is_not_at_spot(self) -> None:
        """移動中の人の試みは NotAtSpot を持つ。"""
        session = _opened_world()
        session.aggregates().whereabouts().start_travel(
            PersonBody(_ALICE), Route(start=SpotId("hall"), passages=(_ROAD,))
        )

        situation = ActorSituation.of(TravelAttempt(_ALICE, spot("hall")), session.facts())

        assert situation.at_spot == NotAtSpot()

    def test_every_handed_item_is_read_with_its_spec(self) -> None:
        """2 つの品物を渡す試みは、品物ごとに種類を持つ。"""
        session = _opened_world()
        rope, lamp = session.facts().inventory(_ALICE).items()
        attempt = ItemHandOverAttempt(_ALICE, (Delivery(rope, _BOB), Delivery(lamp, _BOB)), Openly())

        situation = ActorSituation.of(attempt, session.facts())

        assert dict(situation.item_specs) == {rope: ItemSpecId("rope"), lamp: ItemSpecId("lamp")}

    def test_item_no_longer_in_world_is_left_out(self) -> None:
        """世界に無い品物を指す試みでも例外を投げず、その品物は種類に入らない。"""
        session = _opened_world()

        situation = ActorSituation.of(
            ActionAttemptForTests(actor_id=_ALICE, item=ItemInstanceId("item_99")), session.facts()
        )

        assert dict(situation.item_specs) == {}
