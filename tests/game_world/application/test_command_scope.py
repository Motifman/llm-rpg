from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException
from ai_rpg_world.game_world.domain.objects_and_items import Item, ItemInstanceId, ItemLeftWorldEvent
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldEndedEvent, WorldEnding
from ai_rpg_world.game_world.domain.world_records import WorldFlagRaisedEvent, WorldFlags
from tests.game_world.application.world_for_scope_tests import (
    BELL,
    DOOR,
    ROPE,
    WORLD,
    BatchesReceived,
    OnFlagRaised,
    end_world,
    raise_flag,
    raised,
    store_holding,
)


def _raise_bell_then_end_world(session: WorldSession) -> None:
    raise_flag(BELL)(session)
    end_world(session)


class TestCommandScopeRefusal:
    """CommandScope.run の中で集約が断ったとき、範囲を巻き戻して例外を呼び出し元に返すことを保証する。"""

    def test_refusal_in_scope_leaves_no_change_reaches_caller_and_delivers_nothing(self) -> None:
        """終わった世界で旗を立ててから世界を終わらせようとすると WorldAlreadyEndedException が呼び出し元に届き、旗は立っておらず、受け口にもハンドラにも何も配られない。"""
        store = store_holding(WorldFlags.start(WORLD), WorldEnding(WORLD, True))
        distributor = CommittedEventsDistributor()
        scope = CommandScope(store, distributor)
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)
        handler = OnFlagRaised(scope, BELL, raise_flag(DOOR))
        distributor.register_handler(WorldFlagRaisedEvent, handler)

        with pytest.raises(WorldAlreadyEndedException):
            scope.run(_raise_bell_then_end_world)

        assert raised(store, BELL) is False
        assert receiver.batches == []
        assert handler.handled == 0

    def test_refused_scope_is_counted(self) -> None:
        """集約が断った範囲は、refusals に断った例外の error_code ごとに 1 つ数えられる。"""
        store = store_holding(WorldEnding(WORLD, True))
        scope = CommandScope(store, CommittedEventsDistributor())

        with pytest.raises(WorldAlreadyEndedException):
            scope.run(end_world)

        assert scope.refusals == {"GAME_WORLD.WORLD_ALREADY_ENDED": 1}

    def test_non_domain_exception_rolls_back_reaches_caller_and_is_not_counted_as_refusal(self) -> None:
        """ドメイン例外でない例外は、範囲を巻き戻して呼び出し元に届くが、refusals には数えない。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope = CommandScope(store, CommittedEventsDistributor())

        def raise_bell_then_fail(session: WorldSession) -> None:
            raise_flag(BELL)(session)
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError):
            scope.run(raise_bell_then_fail)

        assert raised(store, BELL) is False
        assert scope.refusals == {}


class TestCommandScopeCommit:
    """CommandScope.run が確定した範囲のイベントを 1 つのまとまりで配ることを保証する。"""

    def test_committed_scope_events_reach_receiver_as_one_batch_in_order(self) -> None:
        """旗を立ててから世界を終わらせて確定すると、受け口には 2 つのイベントが起きた順に 1 つのまとまりで渡る。"""
        store = store_holding(WorldFlags.start(WORLD), WorldEnding.start(WORLD))
        distributor = CommittedEventsDistributor()
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)

        CommandScope(store, distributor).run(_raise_bell_then_end_world)

        assert [[type(event) for event in batch] for batch in receiver.batches] == [
            [WorldFlagRaisedEvent, WorldEndedEvent]
        ]

    def test_item_taken_out_of_world_in_scope_puts_its_event_in_the_batch(self) -> None:
        """範囲の中で品物を世界から出すと、その品物の ItemLeftWorldEvent が確定したまとまりに入る。"""
        rope = ItemInstanceId("rope_1")
        store = store_holding(Item.come_into_world(rope, ROPE, WorldTick(0)))
        distributor = CommittedEventsDistributor()
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)

        CommandScope(store, distributor).run(lambda session: session.aggregates().take_item_out_of_world(rope))

        assert [[type(event) for event in batch] for batch in receiver.batches] == [[ItemLeftWorldEvent]]
        left = receiver.batches[0][0]
        assert isinstance(left, ItemLeftWorldEvent) and left.item == rope

    def test_scope_without_events_hands_nothing_to_receiver(self) -> None:
        """イベントの出ない範囲を確定しても、受け口には何も渡らない。"""
        store = store_holding(WorldFlags.start(WORLD))
        distributor = CommittedEventsDistributor()
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)

        CommandScope(store, distributor).run(lambda session: session.facts().flags().is_raised(BELL))

        assert receiver.batches == []

    def test_run_returns_what_the_work_returns_and_keeps_its_change(self) -> None:
        """run は渡した処理の戻り値を返し、処理の変更は確定して次の範囲で読める。"""
        store = store_holding(WorldFlags.start(WORLD))

        def raise_bell_and_answer(session: WorldSession) -> str:
            raise_flag(BELL)(session)
            return "rang"

        answer = CommandScope(store, CommittedEventsDistributor()).run(raise_bell_and_answer)

        assert answer == "rang"
        assert raised(store, BELL) is True
