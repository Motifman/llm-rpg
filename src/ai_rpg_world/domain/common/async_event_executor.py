"""AsyncEventExecutor - 非同期ハンドラ実行の port (Phase 5)

post-commit orchestration が async handler の実行を委譲する抽象。
in-process adapter や将来の outbox/worker adapter が実装する。
"""
from typing import Protocol, Sequence, Tuple

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler

AsyncDispatchTask = Tuple[DomainEvent, EventHandler[DomainEvent]]


class AsyncEventExecutor(Protocol):
    """非同期ハンドラ実行の port

    イベントとハンドラのペアを受け取り、実行する。直列または並行は実装依存。
    初期段階は直列実行互換を維持し、並行実行は opt-in とする。
    """

    def execute(self, tasks: Sequence[AsyncDispatchTask]) -> None:
        """非同期ハンドラタスクを実行する

        Args:
            tasks: (event, handler) の列。同一イベントに対して複数ハンドラがある場合、
                   各 (event, handler) が 1 要素となる。
        """
        ...
