"""Memory Consolidation の環境設定とオーケストレータ用フック生成。"""

from __future__ import annotations

import os
from typing import Callable

from ai_rpg_world.application.llm.services.memory_consolidation_runner import (
    MemoryConsolidationRunner,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_ENV_CONSOLIDATION_THRESHOLD = "MEMORY_CONSOLIDATION_JOURNAL_THRESHOLD"


def consolidation_journal_threshold_from_env() -> int:
    """ジャーナル合計がこの件数以上で初回 Consolidation を許可。`0` 以下で無効。

    未設定時は 8。解析不能な値は 8 にフォールバック。
    """
    raw = (os.environ.get(_ENV_CONSOLIDATION_THRESHOLD) or "8").strip()
    try:
        v = int(raw)
    except ValueError:
        return 8
    return v


def build_memory_consolidation_hook(
    *, runner: MemoryConsolidationRunner
) -> Callable[[PlayerId], None]:
    if not isinstance(runner, MemoryConsolidationRunner):
        raise TypeError("runner must be MemoryConsolidationRunner")

    def _hook(player_id: PlayerId) -> None:
        runner.run(player_id)

    return _hook
