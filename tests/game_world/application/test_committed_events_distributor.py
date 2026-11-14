from __future__ import annotations

import pytest

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.value_object import FlagId
from ai_rpg_world.game_world.domain.world_progress import WorldEnding
from ai_rpg_world.game_world.domain.world_records import WorldFlagRaisedEvent, WorldFlags
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.application.world_for_scope_tests import (
    BELL,
    DOOR,
    GATE,
    WORLD,
    BatchesReceived,
    OnFlagRaised,
    end_world,
    raise_flag,
    raise_flag_unless_ended,
    raised,
    store_holding,
)


def _wired(store: SqliteWorldStore) -> tuple[CommandScope, CommittedEventsDistributor]:
    distributor = CommittedEventsDistributor()
    return CommandScope(store, distributor), distributor


def _fail(session: WorldSession) -> None:
    raise RuntimeError("bug in a handler")


class TestHandlerRefusal:
    """ハンドラが断られたとき、そのハンドラの分だけが巻き戻ることを保証する。"""

    def test_refused_handler_keeps_original_change_rolls_back_its_own_and_lets_others_run(self) -> None:
        """終わった世界で鐘の旗が立つと、扉の旗を立ててから世界を終わらせるハンドラは断られて扉の旗が立たず、鐘の旗は残り、あとに登録した門の旗を立てるハンドラは動く。"""
        store = store_holding(WorldFlags.start(WORLD), WorldEnding(WORLD, True))
        scope, distributor = _wired(store)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, raise_flag(DOOR), end_world))
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, raise_flag(GATE)))

        scope.run(raise_flag(BELL))

        assert (raised(store, BELL), raised(store, DOOR), raised(store, GATE)) == (True, False, True)

    def test_refused_handler_is_counted(self) -> None:
        """断られたハンドラは、refused_handlers にハンドラの型の名前と error_code の組で 1 つ数えられ、その範囲も refusals に数えられる。"""
        store = store_holding(WorldFlags.start(WORLD), WorldEnding(WORLD, True))
        scope, distributor = _wired(store)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, end_world))

        scope.run(raise_flag(BELL))

        assert distributor.refused_handlers == {("OnFlagRaised", "GAME_WORLD.WORLD_ALREADY_ENDED"): 1}
        assert scope.refusals == {"GAME_WORLD.WORLD_ALREADY_ENDED": 1}

    def test_handler_failing_without_domain_exception_reaches_the_caller(self) -> None:
        """ドメイン例外でない例外を投げたハンドラは、断られたハンドラに数えず、例外を最初の run の呼び出し元に届ける。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope, distributor = _wired(store)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, _fail))

        with pytest.raises(RuntimeError):
            scope.run(raise_flag(BELL))

        assert distributor.refused_handlers == {}

    def test_events_of_next_scope_are_distributed_after_a_handler_failed(self) -> None:
        """ハンドラがドメイン例外でない例外を投げたあとでも、次に確定した範囲のイベントは受け口に渡る。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope, distributor = _wired(store)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, _fail))
        receiver = BatchesReceived()
        with pytest.raises(RuntimeError):
            scope.run(raise_flag(BELL))
        distributor.register_receiver(receiver)

        scope.run(raise_flag(DOOR))

        assert receiver.raised_flags() == [[DOOR.flag_id]]

    def test_batches_waiting_when_a_handler_failed_are_not_mixed_into_the_next_scope(self) -> None:
        """鐘で扉の旗を立てたハンドラのまとまりが待っているあいだに、別のハンドラがドメイン例外でない例外を投げると、待っていた扉のまとまりは次に確定した範囲と一緒に配られない。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope, distributor = _wired(store)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, raise_flag(DOOR)))
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, _fail))
        receiver = BatchesReceived()
        with pytest.raises(RuntimeError):
            scope.run(raise_flag(BELL))
        distributor.register_receiver(receiver)

        scope.run(raise_flag(GATE))

        assert receiver.raised_flags() == [[GATE.flag_id]]


class TestEventsFromHandlers:
    """ハンドラの範囲が出したイベントを、新しいまとまりとして同じように配ることを保証する。"""

    def test_events_from_a_handler_reach_receiver_and_handlers_as_separate_batches(self) -> None:
        """鐘で扉の旗を立てるハンドラと、扉で門の旗を立てるハンドラがあると、受け口には鐘・扉・門のまとまりが別々に順に渡る。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope, distributor = _wired(store)
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, raise_flag(DOOR)))
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, DOOR, raise_flag(GATE)))

        scope.run(raise_flag(BELL))

        assert receiver.raised_flags() == [
            [BELL.flag_id],
            [DOOR.flag_id],
            [GATE.flag_id],
        ]


class TestHandlerRegistrationOrder:
    """同じイベントを受けるハンドラの登録の順が、結果を変えないことを保証する。"""

    @pytest.mark.parametrize("door_handler_first", [True, False])
    def test_reaction_to_one_handler_runs_after_every_handler_of_the_same_event(self, door_handler_first: bool) -> None:
        """鐘で扉の旗を立てるハンドラと、鐘で世界を終わらせるハンドラをどちらの順に登録しても、扉の旗に反応して終わっていなければ門の旗を立てるハンドラは、世界が終わったあとに動き、門の旗は立たない。"""
        store = store_holding(WorldFlags.start(WORLD), WorldEnding.start(WORLD))
        scope, distributor = _wired(store)
        same_event: list[EventHandler[WorldFlagRaisedEvent]] = [
            OnFlagRaised(scope, BELL, raise_flag(DOOR)),
            OnFlagRaised(scope, BELL, end_world),
        ]
        for handler in same_event if door_handler_first else reversed(same_event):
            distributor.register_handler(WorldFlagRaisedEvent, handler)
        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, DOOR, raise_flag_unless_ended(GATE)))

        scope.run(raise_flag(BELL))

        assert (raised(store, DOOR), raised(store, GATE)) == (True, False)


class TestReceiverBeforeHandlers:
    """1 つのまとまりを、ハンドラより先に受け口に渡すことを保証する。"""

    def test_receiver_holds_the_batch_when_its_handler_runs(self) -> None:
        """鐘の旗が立ったまとまりでハンドラが動くとき、受け口はそのまとまりをすでに受け取っている。"""
        store = store_holding(WorldFlags.start(WORLD))
        scope, distributor = _wired(store)
        receiver = BatchesReceived()
        distributor.register_receiver(receiver)
        received_when_handled: list[list[list[FlagId]]] = []

        def note_received(session: WorldSession) -> None:
            received_when_handled.append(receiver.raised_flags())

        distributor.register_handler(WorldFlagRaisedEvent, OnFlagRaised(scope, BELL, note_received))

        scope.run(raise_flag(BELL))

        assert received_when_handled == [[[BELL.flag_id]]]
