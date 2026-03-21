"""InProcessAsyncEventTransport - envelope を Executor へ即委譲する transport (Phase 8)

AsyncEventTransport port の in-process 実装。
dispatch で受け取った envelope をそのまま AsyncEventExecutor に渡す。
将来 outbox 実装と差し替え可能な production 差し替え点として本モジュールを挿入する。
SEAM.md の「Transport を production path に接続」に従う。
"""
from typing import Sequence

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask, AsyncEventExecutor
from ai_rpg_world.domain.common.async_event_transport import AsyncEventTransport


class InProcessAsyncEventTransport:
    """AsyncEventTransport 契約を満たす in-process 実装

    dispatch で即 Executor に委譲する。outbox 導入時は本実装を
    OutboxAsyncEventTransport 等に差し替える。差し替えは DI 経由で 1 箇所に閉じる。
    """

    def __init__(self, executor: AsyncEventExecutor) -> None:
        self._executor = executor

    def dispatch(self, envelopes: Sequence[AsyncDispatchTask]) -> None:
        self._executor.execute(envelopes)
