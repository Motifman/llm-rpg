from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.names_in_world import NamesInWorld
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId, WorldId
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
    session.people_register().name(_BOB, DisplayName("ボブ"))
    return design, session


class TestNamesInWorld:
    """NamesInWorld が、場所と品物の名前を世界の宣言から引くことを保証する。"""

    def test_spot_is_named_by_its_declaration(self) -> None:
        """場所の名前は、その場所の宣言の名前になる。"""
        _, session = _opened_world()

        assert NamesInWorld(session.facts()).spot_name(SpotId("hall")) == DisplayName("hall")

    def test_item_is_named_by_its_kind(self) -> None:
        """品物の名前は、その品物の種類の宣言の名前になる。"""
        _, session = _opened_world()
        rope = session.facts().inventory(_BOB).items()[0]

        assert NamesInWorld(session.facts()).item_name(rope) == DisplayName("rope")

    def test_item_that_left_the_world_keeps_its_name(self) -> None:
        """世界から無くなった品物も、無くなる前と同じ種類の名前で引ける。"""
        _, session = _opened_world()
        rope = session.facts().inventory(_BOB).items()[0]
        session.aggregates().item(rope).leave_world()

        assert NamesInWorld(session.facts()).item_name(rope) == DisplayName("rope")
