"""InProcessAsyncEventExecutor - 直列実行の AsyncEventExecutor 実装 (Phase 5)

初期段階は直列実行互換を維持。並行実行は opt-in（将来の拡張で対応）。
"""
from typing import Sequence

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask


class InProcessAsyncEventExecutor:
    """直列実行の in-process AsyncEventExecutor

    post-commit orchestration から委譲された非同期ハンドラタスクを
    順次実行する。既存の同期実行互換を維持する。
    """

    def execute(self, tasks: Sequence[AsyncDispatchTask]) -> None:
        """タスクを直列に実行する"""
        for event, handler in tasks:
            handler.handle(event)
