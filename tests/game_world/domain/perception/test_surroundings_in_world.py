from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.people import PersonRef
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, item_spec, nouns, spot

_WORLD = WorldId("surroundings_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_ROPE = item_spec("rope")


def _opened_world() -> tuple[WorldDesign, WorldSession]:
    bob = replace(character("bob", "hall"), initial_items=(_ROPE.item_spec_id,), initial_held=(_ROPE.item_spec_id,))
    design = compose_world(
        nouns(spots=(spot("hall"),), item_specs=(_ROPE,), characters=(character("alice", "hall"), bob))
    )
    store = SqliteWorldStore.create(
        ":memory:", world_id=_WORLD, scenario="s", scenario_hash="h", design=design, random=SeedableRandomSource(0)
    )
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    session = store.session()
    return design, session


class TestVisibleSurroundingsSeenByPerson:
    """VisibleSurroundings.seen_by_person が、世界の状態からその人の見ている周囲を作ることを保証する。"""

    def test_person_at_spot_sees_the_spot_and_the_people_there(self) -> None:
        """広間にいる起きたアリスには、広間と、そこにいるボブと、ボブの手にある縄が見える。"""
        design, session = _opened_world()
        rope = session.facts().inventory(_BOB).items()[0]

        seen = VisibleSurroundings.seen_by_person(_ALICE, session.facts(), design)

        assert isinstance(seen, VisibleSurroundings)
        assert seen.spot.spot_id == SpotId("hall")
        assert [
            (p.person.appearance.text, p.visible_items) for p in seen.people if isinstance(p.person, PersonRef)
        ] == [("bob の見た目", (rope,))]

    def test_fainted_person_sees_nothing(self) -> None:
        """倒れたアリスには何も見えず、NothingInView になる。"""
        design, session = _opened_world()
        session.aggregates().vitals(_ALICE).take_damage(Damage(999), WorldTick(0), WorldHappening())

        seen = VisibleSurroundings.seen_by_person(_ALICE, session.facts(), design)

        assert isinstance(seen, NothingInView)
