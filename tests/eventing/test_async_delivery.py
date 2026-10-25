"""非同期の受け手が本人ごとの順序と、結果を反映するスレッドを守る。"""

from datetime import datetime, timezone
from threading import Event, get_ident

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.eventing.async_delivery import AsyncEventExecutor


@pytest.mark.parametrize("_repeat", range(3))
def test_slow_handler_does_not_block_submission(_repeat: int) -> None:
    """受け手が停止中でも受付は戻り、結果の反映は受け取る側のスレッドで行う。"""
    entered, release = Event(), Event()
    applied: list[tuple[int, int]] = []
    caller = get_ident()
    executor = AsyncEventExecutor(failure_observer=lambda failure: None)

    def work(event: DomainEvent) -> int:
        entered.set()
        assert release.wait(2)
        return event.event_id

    try:
        assert executor.submit(
            key="a", event=DomainEvent(1, datetime.now(timezone.utc)), handler=work,
            apply_result=lambda value: applied.append((value, get_ident())),
        )
        assert entered.wait(2)
        assert applied == []
    finally:
        release.set()
        executor.shutdown(timeout=2)
    executor.apply_results("a")
    assert applied == [(1, caller)]


@pytest.mark.parametrize("_repeat", range(3))
def test_same_recipient_is_serial_and_other_recipient_runs_in_parallel(_repeat: int) -> None:
    """本人 A の先の仕事が止まっている間、A の次の仕事は待ち、本人 B の仕事は動ける。"""
    first_entered, other_entered, release = Event(), Event(), Event()
    order: list[int] = []
    executor = AsyncEventExecutor(failure_observer=lambda failure: None, max_workers=2)

    def work(event: DomainEvent) -> None:
        order.append(event.event_id)
        if event.event_id == 1:
            first_entered.set()
            assert release.wait(2)
        if event.event_id == 3:
            other_entered.set()

    try:
        for key, number in (("a", 1), ("a", 2), ("b", 3)):
            executor.submit(key=key, event=DomainEvent(number, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
            if number == 1:
                assert first_entered.wait(2)
        assert first_entered.wait(2)
        assert other_entered.wait(2)
        assert order == [1, 3]
    finally:
        release.set()
        executor.shutdown(timeout=2)
    assert order == [1, 3, 2]


def test_handler_failure_is_reported_and_next_job_runs() -> None:
    """本人の先の仕事が失敗しても、その失敗を知らせ、次の仕事を止めない。"""
    failures = []
    applied = []
    executor = AsyncEventExecutor(failure_observer=failures.append, max_workers=1)

    def work(event: DomainEvent) -> int:
        if event.event_id == 1:
            raise RuntimeError("failed")
        return event.event_id

    for number in (1, 2):
        executor.submit(key="a", event=DomainEvent(number, datetime.now(timezone.utc)), handler=work, apply_result=applied.append)
    executor.shutdown(timeout=2)
    executor.apply_results("a")
    assert applied == [2]
    assert len(failures) == 1
    assert failures[0].reason == "handler_failed"
    assert str(failures[0].error) == "failed"


def test_dispatcher_can_register_async_receiver() -> None:
    """確定後の非同期登録は、完了した結果を反映の呼び出しまで保留する。"""
    from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee, EventDispatcher
    from ai_rpg_world.eventing.async_delivery import AsyncDelivery

    executor = AsyncEventExecutor(failure_observer=lambda failure: None)
    dispatcher = EventDispatcher[object](failure_observer=lambda *args: None)
    values: list[int] = []
    dispatcher.register_after_commit(
        DomainEvent, lambda event: event.event_id, channel=DeliveryChannel.AUXILIARY,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
        asynchronous=AsyncDelivery(executor, lambda event: "a", values.append),
    )
    dispatcher.handoff([DomainEvent(7, datetime.now(timezone.utc))])
    executor.shutdown(timeout=2)
    assert values == []
    executor.apply_results("a")
    assert values == [7]


def test_async_registration_rejects_durable_retry() -> None:
    """非同期の受付成功を配送完了と誤認しないよう、再送必須との組み合わせを登録時に拒否する。"""
    from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee, EventDispatcher
    from ai_rpg_world.eventing.async_delivery import AsyncDelivery

    executor = AsyncEventExecutor(failure_observer=lambda failure: None)
    try:
        with pytest.raises(ValueError, match="DURABLE_RETRY"):
            EventDispatcher[object](failure_observer=lambda *args: None).register_after_commit(
                DomainEvent, lambda event: None, channel=DeliveryChannel.AUXILIARY,
                guarantee=DeliveryGuarantee.DURABLE_RETRY,
                asynchronous=AsyncDelivery(executor, lambda event: "a", lambda result: None),
            )
    finally:
        executor.shutdown(timeout=2)


def test_capacity_counts_finished_results_until_they_are_applied() -> None:
    """先の結果が反映待ちで次の仕事が実行中なら、両方を未反映の上限に数えて次の受付を断る。"""
    entered, release = Event(), Event()
    failures = []
    executor = AsyncEventExecutor(failure_observer=failures.append, max_pending=2)

    def work(event: DomainEvent) -> int:
        if event.event_id == 2:
            entered.set()
            assert release.wait(2)
        return event.event_id

    try:
        for number in (1, 2):
            executor.submit(key="a", event=DomainEvent(number, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
        assert entered.wait(2)
        assert executor.pending_count == 2
        assert not executor.submit(key="b", event=DomainEvent(3, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
        assert [failure.reason for failure in failures] == ["capacity"]
    finally:
        release.set()
        executor.shutdown(timeout=2)
    executor.apply_results("b")
    assert executor.pending_count == 2
    executor.apply_results("a")
    assert executor.pending_count == 0


@pytest.mark.parametrize("_repeat", range(3))
def test_shutdown_discards_unfinished_jobs_and_rejects_new_jobs(_repeat: int) -> None:
    """終了期限を超えた実行中・待機中の仕事を破棄し、終了後の新しい仕事は拒否して知らせる。"""
    entered, release = Event(), Event()
    failures, applied = [], []
    executor = AsyncEventExecutor(failure_observer=failures.append, max_workers=1)

    def work(event: DomainEvent) -> int:
        entered.set()
        assert release.wait(2)
        return event.event_id

    try:
        for number in (1, 2):
            executor.submit(key="a", event=DomainEvent(number, datetime.now(timezone.utc)), handler=work, apply_result=applied.append)
        assert entered.wait(2)
        executor.shutdown(timeout=0)
        assert not executor.submit(key="a", event=DomainEvent(3, datetime.now(timezone.utc)), handler=work, apply_result=applied.append)
        assert [(failure.reason, failure.event.event_id) for failure in failures] == [
            ("shutdown_timeout", 1), ("shutdown_timeout", 2), ("shutdown", 3)
        ]
    finally:
        release.set()
        # 終了後の受け手を確実に片付け、遅い結果が保留一覧に戻らないことを見る。
        from concurrent.futures import wait
        wait(tuple(executor._futures), timeout=2)
        executor.shutdown(timeout=2)
    executor.apply_all_results()
    assert applied == []
    assert executor.pending_count == 0


def test_failure_observer_is_mandatory() -> None:
    """知らせ先を省略した場合も None を渡した場合も、配送を始める前に拒否する。"""
    with pytest.raises(TypeError):
        AsyncEventExecutor()
    with pytest.raises(TypeError):
        AsyncEventExecutor(failure_observer=None)
