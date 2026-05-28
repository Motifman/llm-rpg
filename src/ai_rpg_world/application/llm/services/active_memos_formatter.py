"""進行中のメモ (active memos) のテキスト整形ユーティリティ。

Issue #188 Phase 1a で導入された未完了メモのテキスト化を、PromptBuilder と
escape_game runtime の双方で再利用できるよう共通関数に集約する。

並列 2 実装で drift する以前の振る舞いを正確に維持する。
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from ai_rpg_world.application.llm.contracts.dtos import MemoEntry


DEFAULT_STALE_AGE_TICKS = 20


def format_active_memos(
    entries: Sequence[MemoEntry] | Iterable[MemoEntry],
    *,
    current_tick: Optional[int],
    stale_age_ticks: int = DEFAULT_STALE_AGE_TICKS,
) -> str:
    """未完了 memo のリストを「進行中のメモ」section 用テキストに整形する。

    各 memo は ``- [STALE] [tick=N, 経過 M tick] content (id: X)`` の形式に変換される。
    entries が空なら空文字を返す (section ごと表示しない用途を想定)。

    Args:
        entries: 未完了 memo のイテラブル
        current_tick: 現在 tick。None なら age 計算をスキップし STALE 判定もしない。
            ``added_at_tick`` が None の memo は時刻形式で fallback
        stale_age_ticks: 経過 tick がこの値以上なら ``[STALE]`` プレフィックスを付与
    """
    entries_list = list(entries)
    if not entries_list:
        return ""

    lines: list[str] = []
    for memo in entries_list:
        stale_prefix = ""
        age_part = ""
        if current_tick is not None and memo.added_at_tick is not None:
            elapsed = current_tick - memo.added_at_tick
            if elapsed < 0:
                elapsed = 0
            age_part = f", 経過 {elapsed} tick"
            if elapsed >= stale_age_ticks:
                stale_prefix = "[STALE] "
        tick_part = (
            f"tick={memo.added_at_tick}"
            if memo.added_at_tick is not None
            else memo.added_at.strftime("%H:%M")
        )
        lines.append(
            f"- {stale_prefix}[{tick_part}{age_part}] {memo.content} (id: {memo.id})"
        )
    return "\n".join(lines)
