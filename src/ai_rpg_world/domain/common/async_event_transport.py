"""AsyncEventTransport - envelope 配送の port (Phase 6)

envelope を実行基盤に渡す責務を抽象化する。
SEAM.md の Executor と Transport の責務分離に従う。
現状は Publisher が直接 Executor に渡すため、本 port は挿入されていない。
将来 outbox を導入する際、in-process 実装（即 Executor へ委譲）と
outbox 実装（永続化 → Worker poll）を差し替え可能にする。
"""
from typing import Protocol, Sequence

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask


class AsyncEventTransport(Protocol):
    """envelope の配送 port

    envelope を受け取り、実行基盤に渡す責務を持つ。
    - in-process: 即 AsyncEventExecutor.execute に委譲
    - outbox: 永続化し、Worker が poll して Executor に渡す
    """

    def dispatch(self, envelopes: Sequence[AsyncDispatchTask]) -> None:
        """envelope を配送する。

        Args:
            envelopes: 配送対象の (event, handler) タスク列。
                       in-process ではそのまま Executor に渡す。
                       outbox ではシリアライズして永続化する。
        """
        ...
