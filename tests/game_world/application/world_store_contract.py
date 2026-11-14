from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldStore
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoWeather
from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration, Finding
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.world_contents_exception import (
    AggregateNotInWorldException,
    AggregateOwnedTwiceException,
    WorldAlreadyStartedException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    Item,
    ItemCameIntoWorldEvent,
    ItemInstanceId,
    ItemLeftWorldEvent,
    ItemSerialCounter,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import PersonVitals
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    FlagId,
    HitPoints,
    ObjectId,
    PersonId,
    SpotId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, WorldEndedEvent, WorldEnding
from ai_rpg_world.game_world.domain.world_records import (
    MissedNotices,
    WorldFlagLoweredEvent,
    WorldFlagRaisedEvent,
    WorldFlags,
)
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    group_decision,
    item_spec,
    nouns,
    obj,
    spot,
)

WORLD = WorldId("contract_world")
BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
_NOW = WorldTimePassing(WorldTick(3))


ALICE = PersonId("alice")
CAVE = SpotId("cave")
ROPE = item_spec("rope")
ROPE_1 = ItemInstanceId("rope_1")
LAMP = obj("lamp", "cave")
VOTE = group_decision("vote")
CARVING = DiscoverableDeclaration(
    discoverable_id=DiscoverableId("wall_carving"),
    spot_id=CAVE,
    found_text=TextWithUnassignedPeople("壁に彫り物がある"),
    condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
    when_found=NoEffect(),
    finding=Finding.ONCE_PER_PERSON,
)


def design_with_bell() -> WorldDesign:
    return compose_world(
        nouns(
            flags=[BELL],
            spots=[spot("cave")],
            characters=[character("alice", "cave")],
            item_specs=[ROPE],
            objects=[LAMP],
            group_decisions=[VOTE],
        ),
        discoverables=[CARVING],
        group_decision_rules=[everyone_votes_on(VOTE)],
    )


class WorldStoreContract(ABC):
    """WorldStore の実装が、実装に依らず守る約束 (persistence.md の「書く時機を差し替えられるようにする」) を保証する。"""

    @abstractmethod
    def empty_store(self, design: WorldDesign) -> WorldStore: ...

    def store_holding(self, design: WorldDesign, *aggregates: AggregateWithMemento) -> WorldStore:
        store = self.empty_store(design)
        store.start_world(aggregates)
        return store

    def test_starting_a_world_already_started_is_refused_and_adds_no_row(self) -> None:
        """始まりの集約を書いた世界にもう一度書こうとすると WorldAlreadyStartedException を投げ、2 度目の集約は世界に入らない。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))

        with pytest.raises(WorldAlreadyStartedException):
            store.start_world([WorldEnding.start(WORLD)])

        with pytest.raises(AggregateNotInWorldException):
            store.session().ending()

    def test_starting_with_two_aggregates_of_one_owner_is_refused_and_writes_nothing(self) -> None:
        """同じ持ち主の同じ種類の集約を 2 つ渡すと AggregateOwnedTwiceException を投げ、ほかの集約も書かない。"""
        store = self.empty_store(design_with_bell())

        with pytest.raises(AggregateOwnedTwiceException):
            store.start_world([WorldEnding.start(WORLD), WorldFlags.start(WORLD), WorldFlags.start(WORLD)])

        with pytest.raises(AggregateNotInWorldException):
            store.session().ending()

    def test_world_left_empty_by_a_refused_start_can_still_be_started(self) -> None:
        """断られた始まりのあとでも、正しい集約で始めれば、その集約を引ける。"""
        store = self.empty_store(design_with_bell())
        with pytest.raises(AggregateOwnedTwiceException):
            store.start_world([WorldFlags.start(WORLD), WorldFlags.start(WORLD)])

        store.start_world([WorldFlags.start(WORLD)])

        assert store.session().facts().flags().is_raised(BELL) is False

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

    def test_item_taken_out_of_world_returns_its_event_and_is_gone_after_commit(self) -> None:
        """範囲の中で品物を世界から出すと、その品物の ItemLeftWorldEvent が commit の戻りに入り、次の範囲では引けない。"""
        store = self.store_holding(design_with_bell(), Item.come_into_world(ROPE_1, ROPE, WorldTick(0)))
        session = store.session()

        session.aggregates().take_item_out_of_world(ROPE_1)
        events = session.commit()

        assert [(type(event), event.item) for event in events] == [(ItemLeftWorldEvent, ROPE_1)]
        with pytest.raises(AggregateNotInWorldException):
            store.session().facts().item(ROPE_1)

    def test_item_taken_out_of_world_cannot_be_read_in_the_same_scope(self) -> None:
        """世界から出した品物を同じ範囲で引くと AggregateNotInWorldException を投げる。"""
        store = self.store_holding(design_with_bell(), Item.come_into_world(ROPE_1, ROPE, WorldTick(0)))
        session = store.session()
        session.aggregates().take_item_out_of_world(ROPE_1)

        with pytest.raises(AggregateNotInWorldException):
            session.facts().item(ROPE_1)

    def test_item_brought_into_world_is_read_after_commit(self) -> None:
        """範囲の中で品物を世界に持ち込むと、ItemCameIntoWorldEvent が commit の戻りに入り、次の範囲で引ける。"""
        store = self.store_holding(design_with_bell(), ItemSerialCounter.start(WORLD))
        session = store.session()

        brought = session.aggregates().bring_item_into_world(ROPE, WorldTick(2))
        events = session.commit()

        assert [type(event) for event in events] == [ItemCameIntoWorldEvent]
        assert store.session().facts().item(brought).item_id == brought

    def test_item_taken_out_then_rolled_back_is_still_in_world(self) -> None:
        """品物を世界から出して roll_back すると、次の範囲でもその品物を引ける。"""
        store = self.store_holding(design_with_bell(), Item.come_into_world(ROPE_1, ROPE, WorldTick(0)))
        session = store.session()
        session.aggregates().take_item_out_of_world(ROPE_1)

        session.roll_back()

        assert store.session().facts().item(ROPE_1).item_id == ROPE_1

    def test_item_brought_in_and_taken_out_in_one_scope_returns_both_events(self) -> None:
        """同じ範囲で品物を持ち込んでから世界から出すと、commit は持ち込みと持ち出しのイベントをその順で返し、品物は残らない。"""
        store = self.store_holding(design_with_bell(), ItemSerialCounter.start(WORLD))
        session = store.session()

        brought = session.aggregates().bring_item_into_world(ROPE, WorldTick(2))
        session.aggregates().take_item_out_of_world(brought)
        events = session.commit()

        assert [type(event) for event in events] == [ItemCameIntoWorldEvent, ItemLeftWorldEvent]
        with pytest.raises(AggregateNotInWorldException):
            store.session().facts().item(brought)

    def test_item_brought_after_a_rolled_back_one_gets_the_same_id(self) -> None:
        """範囲の中で品物を持ち込んで roll_back すると、次の範囲で持ち込んだ品物は、巻き戻した品物と同じ ID になる。"""
        store = self.store_holding(design_with_bell(), ItemSerialCounter.start(WORLD))
        rolled_back_session = store.session()
        rolled_back = rolled_back_session.aggregates().bring_item_into_world(ROPE, WorldTick(2))
        rolled_back_session.roll_back()

        brought = store.session().aggregates().bring_item_into_world(ROPE, WorldTick(2))

        assert brought == rolled_back

    def test_items_brought_in_separate_scopes_get_different_ids(self) -> None:
        """確定した範囲で品物を持ち込んだあと、次の範囲で持ち込んだ品物は前の品物と別の ID になる。"""
        store = self.store_holding(design_with_bell(), ItemSerialCounter.start(WORLD))
        first_session = store.session()
        first = first_session.aggregates().bring_item_into_world(ROPE, WorldTick(2))
        first_session.commit()

        second = store.session().aggregates().bring_item_into_world(ROPE, WorldTick(3))

        assert second != first

    def test_bringing_an_item_into_a_world_without_a_serial_counter_is_refused(self) -> None:
        """番号の帳簿を入れずに始めた世界で品物を持ち込むと AggregateNotInWorldException を投げる。"""
        store = self.store_holding(design_with_bell())

        with pytest.raises(AggregateNotInWorldException):
            store.session().aggregates().bring_item_into_world(ROPE, WorldTick(2))

    def test_person_vitals_are_read_back_by_person(self) -> None:
        """入れた人の体は、その人の ID で引くと、入れたときと同じ memento で読める。"""
        vitals = PersonVitals.start(ALICE, HitPoints(80, 100))
        store = self.store_holding(design_with_bell(), vitals)

        assert store.session().facts().vitals(ALICE).memento() == vitals.memento()

    def test_person_inventory_is_read_back_by_person(self) -> None:
        """入れた人の持ち物は、その人の ID で引くと、入れたときと同じ memento で読める。"""
        inventory = PersonInventory.start(ALICE, Capacity(20))
        store = self.store_holding(design_with_bell(), inventory)

        assert store.session().facts().inventory(ALICE).memento() == inventory.memento()

    def test_missed_notices_are_read_back_by_person(self) -> None:
        """入れた人の取り逃した知らせは、その人の ID で引くと、入れたときと同じ memento で読める。"""
        notices = MissedNotices.start(ALICE)
        store = self.store_holding(design_with_bell(), notices)

        assert store.session().facts().missed_notices(ALICE).memento() == notices.memento()

    def test_object_state_is_read_back_by_object(self) -> None:
        """入れた物の状態は、その物の ID で引くと、入れたときと同じ memento で読める。"""
        state = ObjectState.from_declaration(LAMP, WorldTick(0))
        store = self.store_holding(design_with_bell(), state)

        assert store.session().facts().object_state(ObjectId("lamp")).memento() == state.memento()

    def test_ground_items_are_read_back_by_spot(self) -> None:
        """入れた場所の地面の品物は、その場所の ID で引くと、入れたときと同じ memento で読める。"""
        ground = GroundItems.start(CAVE)
        ground.place(ROPE_1)
        store = self.store_holding(design_with_bell(), ground)

        assert store.session().facts().ground_items(CAVE).memento() == ground.memento()

    def test_search_progress_with_a_finder_is_read_back_by_spot(self) -> None:
        """その場所で宣言された見つかるものを誰かが見つけた探索の進み具合は、場所の ID で引くと、入れたときと同じ memento で読める。"""
        progress = SpotSearchProgress.start(CAVE)
        progress.record_search(ALICE)
        progress.mark_found(CARVING, ALICE)
        store = self.store_holding(design_with_bell(), progress)

        assert store.session().facts().search_progress(CAVE).memento() == progress.memento()

    def test_group_decision_is_read_back_by_declaration(self) -> None:
        """入れた集団の決定は、その宣言で引くと、入れたときと同じ memento で読める。"""
        decision = GroupDecision.not_started(VOTE)
        store = self.store_holding(design_with_bell(), decision)

        assert store.session().facts().group_decision(VOTE).memento() == decision.memento()

    def test_refused_attempt_apart_undoes_only_its_own_change_and_events(self) -> None:
        """旗を立ててから、小さな範囲の中で世界を 2 度終わらせようとして断られると、終わりも WorldEndedEvent も残らず、範囲の前に立てた旗とそのイベントは残り、断った理由の RefusalCode を返す。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD), WorldEnding.start(WORLD))
        session = store.session()
        session.aggregates().flags().raise_flag(BELL, _NOW)

        def end_twice() -> None:
            session.ending().end(WorldTick(3))
            session.ending().end(WorldTick(3))

        answer = session.attempt_apart(end_twice)
        ended = session.ending().has_ended()
        events = session.commit()

        assert answer == RefusalCode("GAME_WORLD.WORLD_ALREADY_ENDED")
        assert ended is False
        assert [type(event) for event in events] == [WorldFlagRaisedEvent]
        assert store.session().facts().flags().is_raised(BELL) is True

    def test_accepted_attempt_apart_keeps_its_change_and_events_in_order_with_earlier_ones(self) -> None:
        """旗を立ててから、小さな範囲の中で世界を終わらせて通ると、NoRefusal を返し、commit は範囲の前と中のイベントを起きた順に返す。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD), WorldEnding.start(WORLD))
        session = store.session()
        session.aggregates().flags().raise_flag(BELL, _NOW)

        answer = session.attempt_apart(lambda: session.ending().end(WorldTick(3)))
        session.aggregates().flags().lower_flag(BELL, _NOW)
        events = session.commit()

        assert answer == NoRefusal()
        assert [type(event) for event in events] == [WorldFlagRaisedEvent, WorldEndedEvent, WorldFlagLoweredEvent]
        assert store.session().ending().has_ended() is True

    def test_item_brought_in_a_refused_attempt_apart_leaves_no_item_and_no_number_used(self) -> None:
        """小さな範囲の中で品物を持ち込んでから断られると、その品物は世界に無く、次に持ち込んだ品物は巻き戻した品物と同じ ID になる。"""
        store = self.store_holding(design_with_bell(), ItemSerialCounter.start(WORLD), WorldEnding(WORLD, True))
        session = store.session()
        brought: list[ItemInstanceId] = []

        def bring_then_be_refused() -> None:
            brought.append(session.aggregates().bring_item_into_world(ROPE, WorldTick(2)))
            session.ending().end(WorldTick(2))

        session.attempt_apart(bring_then_be_refused)

        with pytest.raises(AggregateNotInWorldException):
            session.facts().item(brought[0])
        assert session.aggregates().bring_item_into_world(ROPE, WorldTick(2)) == brought[0]

    def test_item_taken_out_before_a_refused_attempt_apart_stays_out_with_its_event(self) -> None:
        """品物を世界から出したあとの小さな範囲が断られても、品物は世界に戻らず、commit は ItemLeftWorldEvent を返す。"""
        store = self.store_holding(
            design_with_bell(), Item.come_into_world(ROPE_1, ROPE, WorldTick(0)), WorldEnding(WORLD, True)
        )
        session = store.session()
        session.aggregates().take_item_out_of_world(ROPE_1)

        session.attempt_apart(lambda: session.ending().end(WorldTick(2)))
        events = session.commit()

        assert [type(event) for event in events] == [ItemLeftWorldEvent]
        with pytest.raises(AggregateNotInWorldException):
            store.session().facts().item(ROPE_1)

    def test_refused_attempt_apart_inside_another_undoes_only_the_inner_change(self) -> None:
        """小さな範囲の中で旗を立て、その中のもう 1 つの小さな範囲が断られると、内側の分だけが巻き戻り、外側で立てた旗は残る。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD), WorldEnding(WORLD, True))
        session = store.session()

        def raise_then_be_refused_inside() -> None:
            session.aggregates().flags().raise_flag(BELL, _NOW)
            session.attempt_apart(lambda: session.ending().end(WorldTick(3)))

        outer = session.attempt_apart(raise_then_be_refused_inside)
        events = session.commit()

        assert outer == NoRefusal()
        assert [type(event) for event in events] == [WorldFlagRaisedEvent]

    def test_non_domain_exception_in_attempt_apart_reaches_the_caller(self) -> None:
        """小さな範囲の中でドメイン例外でない例外が起きると、断りとして返さず、そのまま呼び出し元に届く。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()

        def fail() -> None:
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError):
            session.attempt_apart(fail)

    def test_item_taken_out_in_a_refused_attempt_apart_stays_in_world(self) -> None:
        """小さな範囲の中で品物を世界から出してから断られると、品物は世界に残り、commit は ItemLeftWorldEvent を返さない。"""
        store = self.store_holding(
            design_with_bell(), Item.come_into_world(ROPE_1, ROPE, WorldTick(0)), WorldEnding(WORLD, True)
        )
        session = store.session()

        def take_out_then_be_refused() -> None:
            session.aggregates().take_item_out_of_world(ROPE_1)
            session.ending().end(WorldTick(2))

        session.attempt_apart(take_out_then_be_refused)
        events = session.commit()

        assert events == ()
        assert store.session().facts().item(ROPE_1).item_id == ROPE_1

    def test_refused_attempt_apart_drops_events_of_an_accepted_one_inside_it(self) -> None:
        """小さな範囲の中で旗を立て、中のもう 1 つの小さな範囲が通ったあと外側が断られると、旗は立っておらず、commit は WorldFlagRaisedEvent を返さない。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD), WorldEnding(WORLD, True))
        session = store.session()

        def raise_then_pass_inside_then_be_refused() -> None:
            session.aggregates().flags().raise_flag(BELL, _NOW)
            session.attempt_apart(lambda: None)
            session.ending().end(WorldTick(3))

        session.attempt_apart(raise_then_pass_inside_then_be_refused)
        raised = session.facts().flags().is_raised(BELL)
        events = session.commit()

        assert raised is False
        assert events == ()

    def test_domain_exception_without_refusal_mark_in_attempt_apart_is_rolled_back_and_reaches_the_caller(self) -> None:
        """小さな範囲の中で旗を立ててから、世界が断った印 (WorldRefusal) の無いドメイン例外が起きると、断りとして返さずに呼び出し元に届き、範囲の中で立てた旗は残らない。"""
        store = self.store_holding(design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()

        def raise_then_break_a_rule() -> None:
            session.aggregates().flags().raise_flag(BELL, _NOW)
            raise ValueOutOfRangeException("a value the design should have refused")

        with pytest.raises(ValueOutOfRangeException):
            session.attempt_apart(raise_then_break_a_rule)

        assert session.facts().flags().is_raised(BELL) is False
