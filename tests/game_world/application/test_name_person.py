from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.name_person import NamePerson, NamePersonCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.exception.people_register_exception import PersonAlreadyNamedException
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, WorldId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_WORLD = WorldId("naming_world")
_GEN = PersonId("gen")


def _scope() -> CommandScope:
    design = compose_world(nouns(spots=[spot("office")], characters=[character("gen", "office")]))
    store = SqliteWorldStore.create(
        ":memory:",
        world_id=_WORLD,
        scenario="naming_world",
        scenario_hash="naming_world",
        design=design,
        random=SeedableRandomSource(0),
    )
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    return CommandScope(store, CommittedEventsDistributor())


def _name_of(scope: CommandScope) -> DisplayName:
    return scope.run(lambda session: session.facts().people_register().name_of(_GEN))


class TestNamePerson:
    """NamePerson が、世界の名簿に人の名前を付け、付け直しは同じ名前なら受け、違う名前なら断ることを保証する。"""

    def test_names_the_person_in_the_register(self) -> None:
        """gen に「ゲン」と名前を付けると、世界の名簿で gen の名前は「ゲン」になる。"""
        scope = _scope()

        NamePerson(scope)(NamePersonCommand(_GEN, DisplayName("ゲン")))

        assert _name_of(scope) == DisplayName("ゲン")

    def test_same_name_again_is_accepted(self) -> None:
        """同じ「ゲン」をもう一度付けても断らず、名前は「ゲン」のまま。"""
        scope = _scope()
        NamePerson(scope)(NamePersonCommand(_GEN, DisplayName("ゲン")))

        NamePerson(scope)(NamePersonCommand(_GEN, DisplayName("ゲン")))

        assert _name_of(scope) == DisplayName("ゲン")

    def test_another_name_is_refused_and_the_first_name_stays(self) -> None:
        """「ゲン」と付けたあとに「ゲンジ」と付けようとすると PersonAlreadyNamedException で断り、名前は「ゲン」のまま。"""
        scope = _scope()
        NamePerson(scope)(NamePersonCommand(_GEN, DisplayName("ゲン")))

        with pytest.raises(PersonAlreadyNamedException):
            NamePerson(scope)(NamePersonCommand(_GEN, DisplayName("ゲンジ")))

        assert _name_of(scope) == DisplayName("ゲン")
