"""非同期のハンドラ (AsyncEventHandler) の 3 つの段が、それぞれ決まったスレッドで動き、失敗を元のイベントとハンドラで知らせることを保証する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import get_ident

import pytest

from ai_rpg_world.eventing import (
    AsyncEventExecutor,
    AsyncEventHandler,
    AsyncFailure,
    DeliveryChannel,
    DeliveryGuarantee,
    DomainEvent,
    EventDispatcher,
)


@dataclass(frozen=True, kw_only=True)
class _Asked(DomainEvent):
    recipient: str
    value: int


@dataclass(frozen=True, kw_only=True)
class _Other(DomainEvent):
    pass


def _asked(value: int, *, recipient: str = "a") -> _Asked:
    return _Asked(event_id=value, occurred_at=datetime.now(timezone.utc), recipient=recipient, value=value)


class _Doubling(AsyncEventHandler[_Asked, int, int]):
    """値を 2 倍にする。どの段がどのスレッドで動いたかを覚える。"""

    def __init__(self, *, fail_in: str | None = None) -> None:
        self.fail_in = fail_in
        self.threads: dict[str, int] = {}
        self.commands: list[int] = []
        self.applied: list[int] = []

    def prepare(self, event: _Asked) -> int:
        self.threads["prepare"] = get_ident()
        if self.fail_in == "prepare":
            raise RuntimeError("prepare failed")
        return event.value * 10

    def handle(self, command: int) -> int:
        self.threads["handle"] = get_ident()
        self.commands.append(command)
        if self.fail_in == "handle":
            raise RuntimeError("handle failed")
        return command * 2

    def apply(self, result: int) -> None:
        self.threads["apply"] = get_ident()
        if self.fail_in == "apply":
            raise RuntimeError("apply failed")
        self.applied.append(result)


class _World:
    def __init__(self, handler: _Doubling) -> None:
        self.failures: list[AsyncFailure] = []
        self.dispatch_failures: list[tuple[object, ...]] = []
        self.executor = AsyncEventExecutor(failure_observer=self.failures.append)
        self.dispatcher = EventDispatcher[object](failure_observer=lambda *args: self.dispatch_failures.append(args))
        self.handler = handler
        self.dispatcher.register_async_after_commit(
            _Asked,
            handler,
            channel=DeliveryChannel.AUXILIARY,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
            executor=self.executor,
            recipient_key=lambda event: event.recipient,
        )

    def hand_off_and_finish(self, *events: DomainEvent) -> None:
        self.dispatcher.handoff(list(events))
        self.executor.shutdown(timeout=2)


class TestStages:
    """3 つの段が、配送器にイベントを渡したスレッド・裏のスレッド・結果を反映するスレッドに分かれて動くことを保証する。"""

    def test_prepare_runs_on_the_handoff_thread_and_handle_runs_on_a_worker_with_the_command(self) -> None:
        """prepare は配送器にイベントを渡したスレッドでコマンドを作り、handle は裏のスレッドでそのコマンドを受け取り、apply は結果を反映するスレッドで結果を受け取る。"""
        world = _World(_Doubling())
        caller = get_ident()

        world.hand_off_and_finish(_asked(3))
        world.executor.apply_results("a")

        assert world.handler.commands == [30]
        assert world.handler.applied == [60]
        assert (world.handler.threads["prepare"], world.handler.threads["apply"]) == (caller, caller)
        assert world.handler.threads["handle"] != caller

    def test_results_are_applied_only_for_the_recipient(self) -> None:
        """結果は、登録のときに渡した鍵 (宛先) ごとに保留され、その宛先を反映したときだけ apply に渡る。"""
        world = _World(_Doubling())

        world.hand_off_and_finish(_asked(1, recipient="a"), _asked(2, recipient="b"))
        world.executor.apply_results("b")

        assert world.handler.applied == [40]

    def test_events_of_other_types_are_not_prepared(self) -> None:
        """登録したイベントの型でないイベントでは、prepare を呼ばない。"""
        world = _World(_Doubling())

        world.hand_off_and_finish(_Other(event_id=1, occurred_at=datetime.now(timezone.utc)))

        assert world.handler.threads == {}


class TestFailures:
    """どの段で失敗しても、元のドメインイベントとハンドラが分かる形で知らせることを保証する。"""

    def test_prepare_failure_is_reported_with_the_event_and_the_handler(self) -> None:
        """prepare が失敗すると、prepare_failed として元のドメインイベントとハンドラと例外を知らせ、裏の仕事は受け付けない。配送器の失敗の知らせ先には届かない。"""
        world = _World(_Doubling(fail_in="prepare"))
        event = _asked(1)

        world.hand_off_and_finish(event)

        (failure,) = world.failures
        assert (failure.reason, failure.event, failure.handler, str(failure.error)) == (
            "prepare_failed",
            event,
            world.handler,
            "prepare failed",
        )
        assert (world.handler.commands, world.dispatch_failures, world.executor.pending_count) == ([], [], 0)

    def test_handle_failure_is_reported_with_the_event_and_the_handler(self) -> None:
        """handle が失敗すると、handler_failed として、元のドメインイベントとハンドラそのものを知らせ、apply は呼ばない。"""
        world = _World(_Doubling(fail_in="handle"))
        event = _asked(1)

        world.hand_off_and_finish(event)
        world.executor.apply_results("a")

        (failure,) = world.failures
        assert (failure.reason, failure.event, failure.handler, str(failure.error)) == (
            "handler_failed",
            event,
            world.handler,
            "handle failed",
        )
        assert world.handler.applied == []

    def test_apply_failure_is_reported_and_the_rest_of_the_results_are_applied(self) -> None:
        """apply が失敗すると、application_failed として元のドメインイベントとハンドラを知らせ、例外は反映した側へ投げず、同じ宛先の残りの結果も続けて反映する。"""

        class _FailsOnFirst(_Doubling):
            def apply(self, result: int) -> None:
                if result == 20:
                    raise RuntimeError("apply failed")
                super().apply(result)

        world = _World(_FailsOnFirst())
        first = _asked(1)
        world.hand_off_and_finish(first, _asked(2))

        world.executor.apply_results("a")

        (failure,) = world.failures
        assert (failure.reason, failure.event, failure.handler, str(failure.error)) == (
            "application_failed",
            first,
            world.handler,
            "apply failed",
        )
        assert world.handler.applied == [40]
        assert world.executor.pending_count == 0

    def test_durable_retry_is_rejected_at_registration(self) -> None:
        """非同期のハンドラと再送必須 (DURABLE_RETRY) の組み合わせは、受け付けただけで届いたと誤認しないよう、登録のときに断る。"""
        executor = AsyncEventExecutor(failure_observer=lambda failure: None)
        try:
            with pytest.raises(ValueError, match="DURABLE_RETRY"):
                EventDispatcher[object](failure_observer=lambda *args: None).register_async_after_commit(
                    _Asked,
                    _Doubling(),
                    channel=DeliveryChannel.AUXILIARY,
                    guarantee=DeliveryGuarantee.DURABLE_RETRY,
                    executor=executor,
                    recipient_key=lambda event: event.recipient,
                )
        finally:
            executor.shutdown(timeout=2)

    def test_rejected_submission_is_reported_with_the_event_and_the_handler(self) -> None:
        """受付を止めたあとに配送器へイベントを渡すと、prepare は動くが仕事は受け付けず、shutdown として元のドメインイベントとハンドラを知らせる。"""
        world = _World(_Doubling())
        world.executor.shutdown(timeout=2)
        event = _asked(1)

        world.dispatcher.handoff([event])

        (failure,) = world.failures
        assert (failure.reason, failure.event, failure.handler) == ("shutdown", event, world.handler)
        assert world.handler.commands == []

    def test_capacity_rejection_is_reported_with_the_event_and_the_handler(self) -> None:
        """受付の上限に届いていると、仕事は受け付けず、capacity として元のドメインイベントとハンドラを知らせる。"""
        failures: list[AsyncFailure] = []
        executor = AsyncEventExecutor(failure_observer=failures.append, max_pending=1)
        dispatcher = EventDispatcher[object](failure_observer=lambda *args: None)
        handler = _Doubling()
        dispatcher.register_async_after_commit(
            _Asked,
            handler,
            channel=DeliveryChannel.AUXILIARY,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
            executor=executor,
            recipient_key=lambda event: event.recipient,
        )
        second = _asked(2)

        dispatcher.handoff([_asked(1), second])
        executor.shutdown(timeout=2)

        (failure,) = failures
        assert (failure.reason, failure.event, failure.handler) == ("capacity", second, handler)


class TestRegistration:
    """register_async_after_commit が、AsyncEventHandler でないものを登録のときに断ることを保証する。"""

    def test_handler_that_is_not_an_async_event_handler_is_rejected(self) -> None:
        """AsyncEventHandler を継承しない呼び出し可能なものを渡すと、TypeError で断る。"""
        executor = AsyncEventExecutor(failure_observer=lambda failure: None)
        try:
            with pytest.raises(TypeError, match="AsyncEventHandler"):
                EventDispatcher[object](failure_observer=lambda *args: None).register_async_after_commit(
                    _Asked,
                    lambda event: None,  # type: ignore[arg-type]
                    channel=DeliveryChannel.AUXILIARY,
                    guarantee=DeliveryGuarantee.BEST_EFFORT,
                    executor=executor,
                    recipient_key=lambda event: event.recipient,
                )
        finally:
            executor.shutdown(timeout=2)
