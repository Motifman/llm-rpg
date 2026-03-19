"""AnyIOAsyncEventExecutor - anyio を用いた AsyncEventExecutor 実装 (Phase 5/9)

anyio.to_thread.run_sync で各ハンドラをスレッドプールで実行する。
初期段階は直列実行互換（1 件ずつ await）。並行実行は opt-in で将来対応。

利用条件（Phase 9 契約）:
  - 同期コンテキストからのみ呼ぶこと。
  - async コンテキスト内（例: async def 内、asyncio.run のコールバック内）から
    呼ぶと anyio.run() が破綻するため、実行時ガードで InvalidOperationError を投げる。
  - default wiring は InProcessAsyncEventExecutor を使用。本 adapter は opt-in で同期専用。
"""
import asyncio
from typing import Sequence

import anyio
from anyio import to_thread

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask
from ai_rpg_world.infrastructure.events.event_executor_exceptions import (
    InvalidOperationError,
)


class AnyIOAsyncEventExecutor:
    """anyio を用いた in-process AsyncEventExecutor（同期専用契約）

    anyio.to_thread.run_sync で各ハンドラをスレッドで実行する。
    直列実行互換を維持（1 件ずつ完了を待つ）。

    利用条件: 同期コンテキストからのみ呼ぶこと。
    async コンテキスト内からの呼び出しは anyio.run() と競合し破綻するため、
    execute() 起動時にガードにより InvalidOperationError を投げる。
    """

    def execute(self, tasks: Sequence[AsyncDispatchTask]) -> None:
        """タスクを直列に実行する（各ハンドラはスレッドプールで実行）

        同期コンテキストからのみ呼ぶこと。async 内からの呼び出しは契約違反。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # No running loop: sync context, OK to proceed
        else:
            raise InvalidOperationError(
                "AnyIOAsyncEventExecutor must be called from synchronous context only. "
                "Calling from async context (e.g. inside async def) causes anyio.run() to fail. "
                "Use InProcessAsyncEventExecutor for in-process default, or ensure post-commit "
                "orchestration runs from sync context."
            )

        async def run_serial() -> None:
            for event, handler in tasks:
                await to_thread.run_sync(
                    (lambda e, h: lambda: h.handle(e))(event, handler)
                )

        anyio.run(run_serial)
