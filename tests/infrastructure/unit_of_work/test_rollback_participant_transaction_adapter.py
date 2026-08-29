"""repository外の可変状態が永続化transactionと同じrollback境界へ参加することを保証する。"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from ai_rpg_world.application.common.exceptions import (
    DuplicateRollbackParticipantException,
    NestedRollbackParticipantTransactionException,
    RollbackParticipantCleanupException,
    RollbackParticipantRestoreException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.application.common.command_scope import CommandCompletion, CommandScope
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionAdapter,
    RollbackParticipantTransactionFactory,
    unwrap_transaction,
)


class _Transaction:
    def __init__(
        self,
        timeline: list[str],
        *,
        begin_error: BaseException | None = None,
        commit_error: BaseException | None = None,
        rollback_error: BaseException | None = None,
        committed_cleanup_error: BaseException | None = None,
    ) -> None:
        self._timeline = timeline
        self._active = False
        self._begin_error = begin_error
        self._commit_error = commit_error
        self._rollback_error = rollback_error
        self._committed_cleanup_error = committed_cleanup_error

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        self._timeline.append("transaction.begin")
        self._active = True
        if self._begin_error is not None:
            raise self._begin_error

    def commit(self) -> None:
        self._timeline.append("transaction.commit")
        if self._commit_error is not None:
            raise self._commit_error
        self._active = False
        if self._committed_cleanup_error is not None:
            raise TransactionCommittedCleanupException(
                cleanup_error=self._committed_cleanup_error
            )

    def rollback(self) -> None:
        self._timeline.append("transaction.rollback")
        self._active = False
        if self._rollback_error is not None:
            raise self._rollback_error


class _TransactionFactory:
    def __init__(self, transaction: _Transaction) -> None:
        self._transaction = transaction
        self.create_count = 0

    def create(self) -> _Transaction:
        self.create_count += 1
        return self._transaction


class _Participant:
    def __init__(
        self,
        name: str,
        timeline: list[str],
        *,
        resource: object | None = None,
        value: Any = 0,
        snapshot_error: BaseException | None = None,
        restore_error: BaseException | None = None,
        acquire_error: BaseException | None = None,
        release_error: BaseException | None = None,
    ) -> None:
        self.name = name
        self._timeline = timeline
        self._resource = resource if resource is not None else self
        self.value = value
        self._snapshot_error = snapshot_error
        self._restore_error = restore_error
        self._acquire_error = acquire_error
        self._release_error = release_error
        self.poison_errors: list[BaseException] = []
        self._ownership_lock = threading.Lock()
        self.ownership_acquire_count = 0
        self.ownership_release_count = 0

    @property
    def rollback_resource(self) -> object:
        return self._resource

    def acquire_rollback_ownership(self) -> None:
        if self._acquire_error is not None:
            raise self._acquire_error
        self._ownership_lock.acquire()
        self.ownership_acquire_count += 1

    def release_rollback_ownership(self) -> None:
        self._ownership_lock.release()
        self.ownership_release_count += 1
        if self._release_error is not None:
            raise self._release_error

    def take_rollback_snapshot(self) -> Any:
        self._timeline.append(f"{self.name}.snapshot")
        if self._snapshot_error is not None:
            raise self._snapshot_error
        return self.value

    def restore_rollback_snapshot(self, snapshot: Any) -> None:
        self._timeline.append(f"{self.name}.restore")
        if self._restore_error is not None:
            raise self._restore_error
        self.value = snapshot

    def poison_after_rollback_failure(self, error: BaseException) -> None:
        self._timeline.append(f"{self.name}.poison")
        self.poison_errors.append(error)


class TestRollbackParticipantTransactionAdapter:
    """参加資源のsnapshot・復元・確定順序と失敗情報を保証する。"""

    def test_commit_keeps_participant_changes(self) -> None:
        """正常commitでは開始前snapshotを復元せずcommand中の変更を保持する。"""
        timeline: list[str] = []
        transaction = _Transaction(timeline)
        participant = _Participant("flags", timeline, value={"before"})
        adapter = RollbackParticipantTransactionAdapter(
            transaction,
            participants=(participant,),
        )

        adapter.begin()
        participant.value = {"after"}
        adapter.commit()

        assert participant.value == {"after"}
        assert timeline == [
            "transaction.begin",
            "flags.snapshot",
            "transaction.commit",
        ]
        assert adapter.is_active is False

    def test_rollback_restores_participants_in_reverse_order(self) -> None:
        """command失敗では永続化を戻した後、参加資源を登録と逆順で復元する。"""
        timeline: list[str] = []
        transaction = _Transaction(timeline)
        first = _Participant("flags", timeline, value="before-flags")
        second = _Participant("cooldown", timeline, value="before-cooldown")
        adapter = RollbackParticipantTransactionAdapter(
            transaction,
            participants=(first, second),
        )

        adapter.begin()
        first.value = "after-flags"
        second.value = "after-cooldown"
        adapter.rollback()

        assert first.value == "before-flags"
        assert second.value == "before-cooldown"
        assert timeline == [
            "transaction.begin",
            "flags.snapshot",
            "cooldown.snapshot",
            "transaction.rollback",
            "cooldown.restore",
            "flags.restore",
        ]

    def test_begin_error_can_be_rolled_back_before_participant_snapshot(self) -> None:
        """永続化begin途中の失敗では参加資源へ触れず、基底transactionだけを戻す。"""
        timeline: list[str] = []
        begin_error = RuntimeError("begin failed")
        transaction = _Transaction(timeline, begin_error=begin_error)
        participant = _Participant("graph", timeline, value="before")
        adapter = RollbackParticipantTransactionAdapter(
            transaction,
            participants=(participant,),
        )

        with pytest.raises(RuntimeError) as caught:
            adapter.begin()

        assert caught.value is begin_error
        assert adapter.is_active is True

        adapter.rollback()

        assert participant.value == "before"
        assert adapter.is_active is False
        assert timeline == [
            "transaction.begin",
            "transaction.rollback",
        ]

    def test_snapshot_error_leaves_active_for_command_scope_rollback(self) -> None:
        """snapshot取得失敗では排他済みtransactionをactiveに保ってrollback可能にする。"""
        timeline: list[str] = []
        snapshot_error = RuntimeError("snapshot failed")
        transaction = _Transaction(timeline)
        participant = _Participant(
            "flags",
            timeline,
            snapshot_error=snapshot_error,
        )
        adapter = RollbackParticipantTransactionAdapter(
            transaction,
            participants=(participant,),
        )

        with pytest.raises(RuntimeError) as caught:
            adapter.begin()

        assert caught.value is snapshot_error
        assert timeline == ["transaction.begin", "flags.snapshot"]
        assert adapter.is_active is True

        adapter.rollback()

        assert timeline == [
            "transaction.begin",
            "flags.snapshot",
            "transaction.rollback",
        ]
        assert adapter.is_active is False

    def test_committed_cleanup_error_does_not_restore_participant(self) -> None:
        """基底commit成功後のcleanup失敗では参加資源を開始前へ戻さない。"""
        timeline: list[str] = []
        cleanup_error = RuntimeError("close failed")
        participant = _Participant("flags", timeline, value="before")
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline, committed_cleanup_error=cleanup_error),
            participants=(participant,),
        )
        adapter.begin()
        participant.value = "after"

        with pytest.raises(TransactionCommittedCleanupException) as caught:
            adapter.commit()

        assert caught.value.cleanup_error is cleanup_error
        assert participant.value == "after"
        assert adapter.is_active is False

    def test_commit_failure_keeps_snapshot_for_following_rollback(self) -> None:
        """commit未完了の例外後は参加資源を開始前へ復元できる。"""
        timeline: list[str] = []
        commit_error = RuntimeError("commit failed")
        participant = _Participant("flags", timeline, value="before")
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline, commit_error=commit_error),
            participants=(participant,),
        )
        adapter.begin()
        participant.value = "after"

        with pytest.raises(RuntimeError) as caught:
            adapter.commit()

        assert caught.value is commit_error
        assert adapter.is_active is True

        adapter.rollback()

        assert participant.value == "before"
        assert adapter.is_active is False

    def test_later_snapshot_failure_restores_already_snapshotted_resource(self) -> None:
        """2番目のsnapshot失敗では取得済みの1番目をrollback時に復元する。"""
        timeline: list[str] = []
        snapshot_error = RuntimeError("second snapshot failed")
        first = _Participant("flags", timeline, value="before")
        second = _Participant(
            "cooldown",
            timeline,
            snapshot_error=snapshot_error,
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(first, second),
        )

        with pytest.raises(RuntimeError) as caught:
            adapter.begin()

        assert caught.value is snapshot_error
        first.value = "changed-after-snapshot"
        adapter.rollback()

        assert first.value == "before"
        assert adapter.is_active is False

    def test_resource_ownership_serializes_snapshot_until_completion(self) -> None:
        """同じ資源の後続commandは先行rollback完了後の値をsnapshotに取る。"""
        timeline: list[str] = []
        participant = _Participant("flags", timeline, value=0)
        first = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(participant,),
        )
        second = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(participant,),
        )
        second_started = threading.Event()
        second_acquired = threading.Event()

        first.begin()
        participant.value = 1

        def run_second() -> None:
            second_started.set()
            second.begin()
            second_acquired.set()
            participant.value = 2
            second.commit()

        thread = threading.Thread(target=run_second)
        thread.start()
        assert second_started.wait(timeout=1)
        assert second_acquired.wait(timeout=0.05) is False

        first.rollback()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert second_acquired.is_set() is True
        assert participant.value == 2

    def test_reverse_registration_uses_one_global_ownership_order(self) -> None:
        """参加順が逆の2 commandも資源同一性順で占有し相互待ちしない。"""
        timeline: list[str] = []
        first_resource = _Participant("flags", timeline)
        second_resource = _Participant("cooldown", timeline)
        first = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(first_resource, second_resource),
        )
        second = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(second_resource, first_resource),
        )
        second_finished = threading.Event()

        first.begin()

        def run_second() -> None:
            second.begin()
            second.commit()
            second_finished.set()

        thread = threading.Thread(target=run_second)
        thread.start()
        assert second_finished.wait(timeout=0.05) is False

        first.commit()
        thread.join(timeout=1)

        assert thread.is_alive() is False
        assert second_finished.is_set() is True

    def test_partial_ownership_failure_releases_already_acquired_resource(self) -> None:
        """後続資源の占有失敗では取得済み資源をrollbackで必ず解放する。"""
        timeline: list[str] = []
        participants = [
            _Participant("first", timeline),
            _Participant("second", timeline),
        ]
        ordered = sorted(participants, key=lambda item: id(item.rollback_resource))
        acquire_error = RuntimeError("acquire failed")
        ordered[1]._acquire_error = acquire_error
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=participants,
        )

        with pytest.raises(RuntimeError) as caught:
            adapter.begin()

        assert caught.value is acquire_error
        adapter.rollback()

        assert ordered[0].ownership_acquire_count == 1
        assert ordered[0].ownership_release_count == 1
        assert ordered[1].ownership_acquire_count == 0
        assert adapter.is_active is False

    def test_commit_release_failure_is_reported_as_committed_cleanup(self) -> None:
        """commit後の占有解放失敗は変更を戻さず全原因をcleanup例外へ保持する。"""
        timeline: list[str] = []
        release_error = RuntimeError("release failed")
        participant = _Participant(
            "flags",
            timeline,
            value="before",
            release_error=release_error,
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(participant,),
        )
        adapter.begin()
        participant.value = "after"

        with pytest.raises(TransactionCommittedCleanupException) as caught:
            adapter.commit()

        cleanup = caught.value.cleanup_error
        assert isinstance(cleanup, RollbackParticipantCleanupException)
        assert cleanup.transaction_cleanup_error is None
        assert cleanup.participant_errors == ((participant, release_error),)
        assert participant.value == "after"
        assert participant.poison_errors == [release_error]
        assert adapter.is_active is False

    def test_base_cleanup_and_release_failure_are_both_preserved(self) -> None:
        """基底cleanupと参加資源の解放が共に失敗しても両原因を失わない。"""
        timeline: list[str] = []
        base_cleanup_error = RuntimeError("base cleanup failed")
        release_error = RuntimeError("release failed")
        participant = _Participant(
            "flags",
            timeline,
            release_error=release_error,
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(
                timeline,
                committed_cleanup_error=base_cleanup_error,
            ),
            participants=(participant,),
        )
        adapter.begin()

        with pytest.raises(TransactionCommittedCleanupException) as caught:
            adapter.commit()

        cleanup = caught.value.cleanup_error
        assert isinstance(cleanup, RollbackParticipantCleanupException)
        assert cleanup.transaction_cleanup_error is base_cleanup_error
        assert cleanup.participant_errors == ((participant, release_error),)

    def test_base_cleanup_control_error_wins_over_normal_release_error(self) -> None:
        """基底cleanupのKeyboardInterruptは解放失敗と重なっても元型で伝播する。"""
        timeline: list[str] = []
        interrupt = KeyboardInterrupt("stop")
        release_error = RuntimeError("release failed")
        participant = _Participant(
            "flags",
            timeline,
            release_error=release_error,
        )
        scope = CommandScope(
            RollbackParticipantTransactionAdapter(
                _Transaction(
                    timeline,
                    committed_cleanup_error=interrupt,
                ),
                participants=(participant,),
            ),
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_NoOpHandoff(),
        )

        with pytest.raises(KeyboardInterrupt) as caught:
            with scope:
                pass

        assert caught.value is interrupt
        assert scope.completion is CommandCompletion.COMMITTED
        cleanup = getattr(interrupt, "rollback_participant_cleanup_error")
        assert isinstance(cleanup, RollbackParticipantCleanupException)
        assert cleanup.transaction_cleanup_error is interrupt
        assert cleanup.participant_errors == ((participant, release_error),)

    def test_rollback_release_failure_poison_resource_and_is_reported(self) -> None:
        """rollback後の占有解放失敗は資源を使用不能にして診断へ残す。"""
        timeline: list[str] = []
        release_error = RuntimeError("release failed")
        participant = _Participant(
            "flags",
            timeline,
            value="before",
            release_error=release_error,
        )
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(participant,),
        )
        adapter.begin()
        participant.value = "after"

        with pytest.raises(RollbackParticipantRestoreException) as caught:
            adapter.rollback()

        assert participant.value == "before"
        assert caught.value.participant_errors == ((participant, release_error),)
        assert participant.poison_errors == [release_error]
        assert adapter.is_active is False

    def test_duplicate_underlying_resource_is_rejected_before_snapshot(self) -> None:
        """同じ可変資源を別adapterで二重登録すると開始前に拒否する。"""
        timeline: list[str] = []
        resource = object()
        first = _Participant("first", timeline, resource=resource)
        second = _Participant("second", timeline, resource=resource)
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(first, second),
        )

        with pytest.raises(DuplicateRollbackParticipantException):
            adapter.begin()

        assert timeline == []
        assert adapter.is_active is False

    def test_restore_failure_poison_resource_and_preserves_all_failures(self) -> None:
        """永続化rollbackと複数資源の復元が失敗しても全原因を保持して全資源を試す。"""
        timeline: list[str] = []
        transaction_error = RuntimeError("transaction rollback failed")
        first_error = RuntimeError("flags restore failed")
        second_error = RuntimeError("cooldown restore failed")
        first = _Participant("flags", timeline, restore_error=first_error)
        second = _Participant("cooldown", timeline, restore_error=second_error)
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline, rollback_error=transaction_error),
            participants=(first, second),
        )
        adapter.begin()

        with pytest.raises(RollbackParticipantRestoreException) as caught:
            adapter.rollback()

        assert caught.value.transaction_error is transaction_error
        assert caught.value.participant_errors == (
            (second, second_error),
            (first, first_error),
        )
        assert second.poison_errors == [second_error]
        assert first.poison_errors == [first_error]
        assert adapter.is_active is False
        assert timeline[-5:] == [
            "transaction.rollback",
            "cooldown.restore",
            "cooldown.poison",
            "flags.restore",
            "flags.poison",
        ]


class TestRollbackParticipantTransactionFactory:
    """commandごとに未開始の参加adapterを一度だけ生成することを保証する。"""

    def test_factory_wraps_each_created_transaction(self) -> None:
        """factoryは基底factoryのtransactionと同じ参加資源を新しいadapterへ束ねる。"""
        timeline: list[str] = []
        transaction = _Transaction(timeline)
        base_factory = _TransactionFactory(transaction)
        participant = _Participant("flags", timeline)
        factory = RollbackParticipantTransactionFactory(
            base_factory,
            participants=(participant,),
        )

        created = factory.create()

        assert isinstance(created, RollbackParticipantTransactionAdapter)
        assert base_factory.create_count == 1

    def test_nested_composition_is_rejected_before_begin(self) -> None:
        """多段合成は全体の重複・占有順を壊すため構築時に拒否する。"""
        timeline: list[str] = []
        transaction = _Transaction(timeline)
        inner = RollbackParticipantTransactionAdapter(
            transaction,
            participants=(_Participant("flags", timeline),),
        )

        with pytest.raises(NestedRollbackParticipantTransactionException):
            RollbackParticipantTransactionAdapter(
                inner,
                participants=(_Participant("cooldown", timeline),),
            )

        assert unwrap_transaction(inner) is transaction


class _NoOpDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        pass


class _NoOpHandoff:
    def handoff(self, events: object) -> None:
        pass


class TestCommandScopeWithRollbackParticipants:
    """CommandScopeが参加資源の開始失敗とcommand失敗を同じ規則で戻す。"""

    def test_snapshot_error_rolls_back_underlying_transaction(self) -> None:
        """参加資源のsnapshot失敗時はcommand本体へ入らず基底transactionを戻す。"""
        timeline: list[str] = []
        snapshot_error = RuntimeError("snapshot failed")
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(
                _Participant(
                    "flags",
                    timeline,
                    snapshot_error=snapshot_error,
                ),
            ),
        )
        scope = CommandScope(
            adapter,
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_NoOpHandoff(),
        )

        with pytest.raises(RuntimeError) as caught:
            with scope:
                pytest.fail("snapshot失敗後にcommand本体へ入ってはいけない")

        assert caught.value is snapshot_error
        assert timeline == [
            "transaction.begin",
            "flags.snapshot",
            "transaction.rollback",
        ]

    def test_command_body_error_restores_participant_before_propagation(self) -> None:
        """command本体例外はCommandScope経由で参加資源を復元してから伝播する。"""
        timeline: list[str] = []
        command_error = RuntimeError("command failed")
        participant = _Participant("flags", timeline, value="before")
        adapter = RollbackParticipantTransactionAdapter(
            _Transaction(timeline),
            participants=(participant,),
        )
        scope = CommandScope(
            adapter,
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_NoOpHandoff(),
        )

        with pytest.raises(RuntimeError) as caught:
            with scope:
                participant.value = "after"
                raise command_error

        assert caught.value is command_error
        assert participant.value == "before"
        assert adapter.is_active is False

    def test_release_control_error_keeps_original_type_after_commit(self) -> None:
        """commit後のKeyboardInterruptは通常例外へ変換せず元の型で伝播する。"""
        timeline: list[str] = []
        interrupt = KeyboardInterrupt("stop")
        participant = _Participant(
            "flags",
            timeline,
            release_error=interrupt,
        )
        scope = CommandScope(
            RollbackParticipantTransactionAdapter(
                _Transaction(timeline),
                participants=(participant,),
            ),
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_NoOpHandoff(),
        )

        with pytest.raises(KeyboardInterrupt) as caught:
            with scope:
                pass

        assert caught.value is interrupt
        assert scope.completion is CommandCompletion.COMMITTED
        cleanup = getattr(interrupt, "rollback_participant_cleanup_error")
        assert isinstance(cleanup, RollbackParticipantCleanupException)
