from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ai_rpg_world.game_world.application.world_store import WorldStore
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoWeather
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldEndedEvent, WorldEnding
from ai_rpg_world.game_world.domain.world_records import WorldFlagLoweredEvent, WorldFlagRaisedEvent, WorldFlags
from tests.game_world.support.world_design_for_tests import compose_world, nouns

WORLD = WorldId("contract_world")
BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
_NOW = WorldTimePassing(WorldTick(3))


def design_with_bell() -> WorldDesign:
    return compose_world(nouns(flags=[BELL]))


class WorldStoreContract(ABC):
    """WorldStore の実装が、実装に依らず守る約束 (persistence.md の「書く時機を差し替えられるようにする」) を保証する。"""

    @abstractmethod
    def store_holding(self, design: WorldDesign, *aggregates: object) -> WorldStore: ...

    def test_flag_raised_in_scope_is_read_in_scope_and_after_commit(self) -> None:
        """範囲の中で旗を立てると、同じ範囲の facts で立っていると読め、commit のあと別の範囲でも読める。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))

        session = store.session()
        session.aggregates().flags().raise_flag(BELL, _NOW)
        read_in_scope = session.facts().flags().is_raised(BELL)
        session.commit()
        read_after_commit = store.session().facts().flags().is_raised(BELL)

        assert read_in_scope is True
        assert read_after_commit is True

    def test_roll_back_leaves_nothing_and_drops_events(self) -> None:
        """旗を立てて roll_back すると、次の範囲では立っておらず、次の commit もそのイベントを返さない。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))
        rolled_back = store.session()
        rolled_back.aggregates().flags().raise_flag(BELL, _NOW)

        rolled_back.roll_back()
        next_session = store.session()
        raised = next_session.facts().flags().is_raised(BELL)
        events = next_session.commit()

        assert raised is False
        assert events == ()

    def test_commit_returns_events_of_two_aggregates_in_the_order_they_occurred(self) -> None:
        """旗を立て、世界を終わらせ、旗を降ろすと、commit は集約をまたいでその順にイベントを返す。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD), WorldEnding.start(WORLD))
        session = store.session()

        session.aggregates().flags().raise_flag(BELL, _NOW)
        session.ending().end(WorldTick(3))
        session.aggregates().flags().lower_flag(BELL, _NOW)
        events = session.commit()

        assert [type(event) for event in events] == [WorldFlagRaisedEvent, WorldEndedEvent, WorldFlagLoweredEvent]

    def test_committed_events_are_not_returned_again(self) -> None:
        """commit で返したイベントは、次の範囲の commit では返らない。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))
        first = store.session()
        first.aggregates().flags().raise_flag(BELL, _NOW)
        first.commit()

        second = store.session()
        second.facts().flags()
        events = second.commit()

        assert events == ()

    def test_aggregate_missing_from_world_raises_and_is_not_created(self) -> None:
        """世界に無い集約を引くと AggregateNotInWorldException を投げ、次の範囲でも作られていない。"""
        store = self.store_holding(design_with_bell())
        first = store.session()

        with pytest.raises(AggregateNotInWorldException):
            first.facts().flags()
        first.commit()

        with pytest.raises(AggregateNotInWorldException):
            store.session().facts().flags()

    def test_world_without_weather_reads_no_weather_and_refuses_to_change_it(self) -> None:
        """天候を宣言しない世界では、facts の weather は NoWeather を返し、aggregates の weather は例外を投げる。"""
        store = self.store_holding(design_with_bell())
        session = store.session()

        weather = session.facts().weather()

        assert isinstance(weather, NoWeather)
        with pytest.raises(AggregateNotInWorldException):
            session.aggregates().weather()
