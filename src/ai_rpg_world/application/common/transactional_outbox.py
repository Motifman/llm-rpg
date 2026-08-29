"""commandの確定イベントをtransaction内outboxへ登録する契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Sequence

from ai_rpg_world.domain.common.domain_event import DomainEvent

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import TransactionPort


@dataclass(frozen=True)
class StagedOutboxBatch:
    """1 commandでoutboxへ登録したイベントIDの不変な集合。"""

    event_ids: tuple[str, ...]


class TransactionalOutboxPort(Protocol):
    """commit前登録とcommit後の配達済み記録を分離するport。"""

    def stage(
        self,
        events: Sequence[DomainEvent],
        transaction: "TransactionPort",
    ) -> StagedOutboxBatch:
        """再送対象イベントを現在のtransactionへ登録する。"""
        ...

    def mark_delivered(self, batch: StagedOutboxBatch) -> None:
        """commit後handoffに成功した登録行を配達済みにする。"""
        ...


__all__ = ["StagedOutboxBatch", "TransactionalOutboxPort"]
