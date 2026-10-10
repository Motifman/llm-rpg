"""active_memos_formatter.format_active_memos のテスト。

本家 PromptBuilder と world_runtime runtime で重複していた整形ロジックを
抽出した共通関数 (Issue #227 後続 HIGH-2)。両 caller が依存するため、
振る舞いを単体テストで固定する。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.services.active_memos_formatter import (
    format_active_memos,
)
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry


def _make_memo(
    id_: str,
    content: str,
    *,
    added_at_tick: int | None = None,
    added_at: datetime | None = None,
) -> MemoEntry:
    return MemoEntry(
        id=id_,
        content=content,
        added_at=added_at or datetime(2026, 1, 1, 10, 30),
        added_at_tick=added_at_tick,
        completed=False,
        completed_at=None,
    )


class TestFormatActiveMemos:
    """format_active_memos の挙動。"""

    def test_empty_entries_returns_empty_string(self) -> None:
        """entries が空なら空文字を返す。"""
        result = format_active_memos([], current_tick=10)
        assert result == ""

    def test_renders_elapsed_time_in_world_minutes(self) -> None:
        """世界の時計で 1 tick 5 分なら、7 tick 前のメモは「経過 35 分」と書き、tick の番号は出さない (#1562)。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=5)

        result = format_active_memos([memo], current_tick=12, minutes_per_tick=5)

        assert result == "- [memo_m1] [経過 35 分] 鍵を探す"

    def test_renders_elapsed_turns_when_clock_is_unknown(self) -> None:
        """分に直せない世界では、経過を手番の回数で書く (#1562)。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=5)

        result = format_active_memos([memo], current_tick=12, minutes_per_tick=None)

        assert result == "- [memo_m1] [経過 手番 7 回ぶん] 鍵を探す"

    def test_marks_stale_when_elapsed_exceeds_threshold(self) -> None:
        """elapsed が stale_age_ticks 以上なら [STALE] プレフィックスが付く。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=0)
        result = format_active_memos(
            [memo], current_tick=25, stale_age_ticks=20, minutes_per_tick=5
        )
        assert result.startswith("- [memo_m1] [STALE] ")

    def test_does_not_mark_stale_below_threshold(self) -> None:
        """elapsed < stale_age_ticks なら [STALE] が付かない。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=0)
        result = format_active_memos(
            [memo], current_tick=10, stale_age_ticks=20, minutes_per_tick=5
        )
        assert "[STALE]" not in result

    def test_negative_elapsed_is_clamped_to_zero(self) -> None:
        """added_at_tick > current_tick なら elapsed を 0 にクランプする (バグ防止)。"""
        memo = _make_memo("m1", "未来のメモ", added_at_tick=100)
        result = format_active_memos([memo], current_tick=10, minutes_per_tick=5)
        assert "経過 0 分" in result

    def test_omits_time_bracket_when_added_tick_is_unknown(self) -> None:
        """added_at_tick=None の memo は、現実の時刻 (added_at) を出さず、時間の括弧ごと省く (#1562)。"""
        memo = _make_memo(
            "m1",
            "メモ",
            added_at_tick=None,
            added_at=datetime(2026, 1, 1, 9, 5),
        )

        result = format_active_memos([memo], current_tick=10, minutes_per_tick=5)

        assert result == "- [memo_m1] メモ"

    def test_omits_time_bracket_when_current_tick_none(self) -> None:
        """current_tick=None なら経過を出さず、追加した時点の tick の番号も出さない (#1562)。"""
        memo = _make_memo("m1", "メモ", added_at_tick=5)

        result = format_active_memos([memo], current_tick=None, minutes_per_tick=5)

        assert result == "- [memo_m1] メモ"

    def test_renders_multiple_memos_separated_by_newline(self) -> None:
        """複数 memo は改行区切り。"""
        m1 = _make_memo("m1", "A", added_at_tick=0)
        m2 = _make_memo("m2", "B", added_at_tick=1)
        result = format_active_memos([m1, m2], current_tick=2)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "A" in lines[0]
        assert "B" in lines[1]
