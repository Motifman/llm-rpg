"""AnyIOAsyncEventExecutor - anyio を用いた AsyncEventExecutor 実装 (Phase 5)

anyio.to_thread.run_sync で各ハンドラをスレッドプールで実行する。
初期段階は直列実行互換（1 件ずつ await）。並行実行は opt-in で将来対応。
"""
from typing import Sequence

import anyio
from anyio import to_thread

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask


class AnyIOAsyncEventExecutor:
    """anyio を用いた in-process AsyncEventExecutor

    anyio.to_thread.run_sync で各ハンドラをスレッドで実行する。
    直列実行互換を維持（1 件ずつ完了を待つ）。
    """

    def execute(self, tasks: Sequence[AsyncDispatchTask]) -> None:
        """タスクを直列に実行する（各ハンドラはスレッドプールで実行）"""

        async def run_serial() -> None:
            for event, handler in tasks:
                await to_thread.run_sync(
                    (lambda e, h: lambda: h.handle(e))(event, handler)
                )

        anyio.run(run_serial)
