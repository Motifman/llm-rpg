"""進行中のメモ (active memos) のテキスト整形ユーティリティ。

Issue #188 Phase 1a で導入された未完了メモのテキスト化を、PromptBuilder と
world_runtime runtime の双方で再利用できるよう共通関数に集約する。

並列 2 実装で drift する以前の振る舞いを正確に維持する。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ai_rpg_world.application.llm.services.memo_id_display import memo_handle
from ai_rpg_world.application.world_graph.interaction_wait_text import span_text
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry

DEFAULT_STALE_AGE_TICKS = 20


def format_active_memos(
    entries: Sequence[MemoEntry] | Iterable[MemoEntry],
    *,
    current_tick: int | None,
    stale_age_ticks: int = DEFAULT_STALE_AGE_TICKS,
    minutes_per_tick: int | None = None,
) -> str:
    """未完了 memo のリストを「進行中のメモ」section 用テキストに整形する。

    各 memo は ``- [memo_X] [STALE] [経過 35 分] content`` の形式に変換される。
    経過は世界の時計の分で書き、tick の番号も現実の時刻も出さない (#1562)。
    経過が分からない memo は時間の括弧ごと省く。
    entries が空なら空文字を返す (section ごと表示しない用途を想定)。

    Args:
        entries: 未完了 memo のイテラブル
        current_tick: 現在 tick。None なら経過を出さず STALE 判定もしない
        stale_age_ticks: 経過 tick がこの値以上なら ``[STALE]`` プレフィックスを付与
        minutes_per_tick: 1 tick が世界の時計で何分か。None なら手番の回数で書く
    """
    entries_list = list(entries)
    if not entries_list:
        return ""

    lines: list[str] = []
    for memo in entries_list:
        stale_prefix = ""
        age_part = ""
        if current_tick is not None and memo.added_at_tick is not None:
            elapsed = max(0, current_tick - memo.added_at_tick)
            age_part = f"[経過{span_text(elapsed, minutes_per_tick)}] "
            if elapsed >= stale_age_ticks:
                stale_prefix = "[STALE] "
        lines.append(
            f"- [{memo_handle(memo.id)}] {stale_prefix}{age_part}{memo.content}"
        )
    return "\n".join(lines)
