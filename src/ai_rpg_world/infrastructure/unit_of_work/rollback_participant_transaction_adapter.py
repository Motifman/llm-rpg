"""repository外の可変状態を既存transactionと同じrollback境界へ束ねる。"""

from __future__ import annotations

from typing import Any, Iterable

from ai_rpg_world.application.common.command_scope import (
    RollbackParticipantPort,
    TransactionPort,
)
from ai_rpg_world.application.common.command_scope_factory import TransactionFactoryPort
from ai_rpg_world.application.common.exceptions import (
    DuplicateRollbackParticipantException,
    NestedRollbackParticipantTransactionException,
    RollbackParticipantCleanupException,
    RollbackParticipantRestoreException,
    TransactionCommittedCleanupException,
)


def unwrap_transaction(transaction: TransactionPort) -> TransactionPort:
    """合成transactionを剥がし、repositoryとoutboxが使う基底資源を返す。"""
    if isinstance(transaction, RollbackParticipantTransactionAdapter):
        return transaction.inner_transaction
    return transaction


class RollbackParticipantTransactionAdapter:
    """既存transactionと複数のsnapshot可能資源を一つのTransactionPortにする。"""

    def __init__(
        self,
        transaction: TransactionPort,
        *,
        participants: Iterable[RollbackParticipantPort],
    ) -> None:
        if isinstance(transaction, RollbackParticipantTransactionAdapter):
            raise NestedRollbackParticipantTransactionException()
        self._transaction = transaction
        self._participants = tuple(participants)
        self._snapshots: list[tuple[RollbackParticipantPort, Any]] = []
        self._owned_participants: list[RollbackParticipantPort] = []
        self._active = False

    @property
    def is_active(self) -> bool:
        """占有開始後から確定または復元完了までTrueを返す。"""
        return self._active

    @property
    def inner_transaction(self) -> TransactionPort:
        """repository providerが元のtransaction資源を特定するための入口。"""
        return self._transaction

    def begin(self) -> None:
        """全参加資源を占有してから基底transactionとsnapshotを開始する。"""
        if self._active:
            raise RuntimeError("rollback参加transactionは開始済みです")
        self._reject_duplicate_resources()
        self._active = True

        # 同じ資源集合を異なる登録順で受けても、全commandが同じ順に占有する。
        # これによりsnapshotから完了までを直列化し、相互待ちも避ける。
        for participant in sorted(
            self._participants,
            key=lambda item: id(item.rollback_resource),
        ):
            participant.acquire_rollback_ownership()
            self._owned_participants.append(participant)

        self._transaction.begin()
        for participant in self._participants:
            self._snapshots.append(
                (participant, participant.take_rollback_snapshot())
            )

    def commit(self) -> None:
        """永続化commit成功時だけsnapshotを破棄し、占有を解放する。"""
        self._require_active("commit")
        committed_cleanup_exception: TransactionCommittedCleanupException | None = None
        try:
            self._transaction.commit()
        except TransactionCommittedCleanupException as error:
            committed_cleanup_exception = error
        except BaseException:
            # CommandScopeが続けてrollbackし、参加資源も復元・解放する。
            raise

        self._snapshots.clear()
        participant_errors = self._release_owned_participants()
        self._active = False
        if committed_cleanup_exception is not None and not participant_errors:
            raise committed_cleanup_exception
        if participant_errors:
            cleanup_error = RollbackParticipantCleanupException(
                transaction_cleanup_error=(
                    committed_cleanup_exception.cleanup_error
                    if committed_cleanup_exception is not None
                    else None
                ),
                participant_errors=tuple(participant_errors),
            )
            cleanup_causes = (
                (
                    committed_cleanup_exception.cleanup_error,
                    *(error for _, error in participant_errors),
                )
                if committed_cleanup_exception is not None
                else tuple(error for _, error in participant_errors)
            )
            control_error = next(
                (
                    error
                    for error in cleanup_causes
                    if not isinstance(error, Exception)
                ),
                None,
            )
            if control_error is not None:
                try:
                    setattr(
                        control_error,
                        "rollback_participant_cleanup_error",
                        cleanup_error,
                    )
                except BaseException:
                    pass
                raise TransactionCommittedCleanupException(
                    cleanup_error=control_error
                ) from cleanup_error
            raise TransactionCommittedCleanupException(
                cleanup_error=cleanup_error
            ) from participant_errors[0][1]

    def rollback(self) -> None:
        """永続化を戻し、参加資源を逆順で復元して占有を解放する。"""
        self._require_active("rollback")
        transaction_error: BaseException | None = None
        participant_errors: list[tuple[object, BaseException]] = []

        try:
            if self._transaction.is_active:
                self._transaction.rollback()
        except BaseException as error:
            transaction_error = error

        for participant, snapshot in reversed(self._snapshots):
            try:
                participant.restore_rollback_snapshot(snapshot)
            except BaseException as error:
                participant_errors.append((participant, error))
                self._poison_participant(participant, error, participant_errors)

        self._snapshots.clear()
        participant_errors.extend(self._release_owned_participants())
        self._active = False
        if transaction_error is not None or participant_errors:
            raise RollbackParticipantRestoreException(
                transaction_error=transaction_error,
                participant_errors=tuple(participant_errors),
            ) from (participant_errors[0][1] if participant_errors else transaction_error)

    def _release_owned_participants(
        self,
    ) -> list[tuple[object, BaseException]]:
        errors: list[tuple[object, BaseException]] = []
        for participant in reversed(self._owned_participants):
            try:
                participant.release_rollback_ownership()
            except BaseException as error:
                errors.append((participant, error))
                self._poison_participant(participant, error, errors)
        self._owned_participants.clear()
        return errors

    @staticmethod
    def _poison_participant(
        participant: RollbackParticipantPort,
        error: BaseException,
        errors: list[tuple[object, BaseException]],
    ) -> None:
        try:
            participant.poison_after_rollback_failure(error)
        except BaseException as poison_error:
            errors.append((participant, poison_error))

    def _reject_duplicate_resources(self) -> None:
        seen_resource_ids: set[int] = set()
        for participant in self._participants:
            resource_id = id(participant.rollback_resource)
            if resource_id in seen_resource_ids:
                raise DuplicateRollbackParticipantException()
            seen_resource_ids.add(resource_id)

    def _require_active(self, operation: str) -> None:
        if self._active:
            return
        raise RuntimeError(
            f"rollback参加transactionが開始されていません: operation={operation}"
        )


class RollbackParticipantTransactionFactory:
    """基底factoryの各transactionを同じrollback参加資源で包む。"""

    def __init__(
        self,
        transaction_factory: TransactionFactoryPort,
        *,
        participants: Iterable[RollbackParticipantPort],
    ) -> None:
        self._transaction_factory = transaction_factory
        self._participants = tuple(participants)

    def create(self) -> RollbackParticipantTransactionAdapter:
        """commandごとに未開始の合成transactionを生成する。"""
        return RollbackParticipantTransactionAdapter(
            self._transaction_factory.create(),
            participants=self._participants,
        )


__all__ = [
    "RollbackParticipantTransactionAdapter",
    "RollbackParticipantTransactionFactory",
    "unwrap_transaction",
]
