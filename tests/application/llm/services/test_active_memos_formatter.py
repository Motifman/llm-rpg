"""active_memos_formatter.format_active_memos のテスト。

本家 PromptBuilder と escape_game runtime で重複していた整形ロジックを
抽出した共通関数 (Issue #227 後続 HIGH-2)。両 caller が依存するため、
振る舞いを単体テストで固定する。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.contracts.dtos import MemoEntry
from ai_rpg_world.application.llm.services.active_memos_formatter import (
    format_active_memos,
)


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

    def test_renders_single_memo_with_tick(self) -> None:
        """tick 付き memo が ``- [tick=N, 経過 M tick] content (id: X)`` に整形される。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=5)
        result = format_active_memos([memo], current_tick=12)
        assert result == "- [tick=5, 経過 7 tick] 鍵を探す (id: m1)"

    def test_marks_stale_when_elapsed_exceeds_threshold(self) -> None:
        """elapsed が stale_age_ticks 以上なら [STALE] プレフィックスが付く。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=0)
        result = format_active_memos(
            [memo], current_tick=25, stale_age_ticks=20
        )
        assert result.startswith("- [STALE] ")

    def test_does_not_mark_stale_below_threshold(self) -> None:
        """elapsed < stale_age_ticks なら [STALE] が付かない。"""
        memo = _make_memo("m1", "鍵を探す", added_at_tick=0)
        result = format_active_memos(
            [memo], current_tick=10, stale_age_ticks=20
        )
        assert "[STALE]" not in result

    def test_negative_elapsed_is_clamped_to_zero(self) -> None:
        """added_at_tick > current_tick なら elapsed を 0 にクランプする (バグ防止)。"""
        memo = _make_memo("m1", "未来のメモ", added_at_tick=100)
        result = format_active_memos([memo], current_tick=10)
        assert "経過 0 tick" in result

    def test_falls_back_to_time_string_when_no_tick(self) -> None:
        """added_at_tick=None の memo は HH:MM 形式で fallback する。"""
        memo = _make_memo(
            "m1",
            "メモ",
            added_at_tick=None,
            added_at=datetime(2026, 1, 1, 9, 5),
        )
        result = format_active_memos([memo], current_tick=10)
        # tick 不明なので age_part は出ない
        assert "[09:05]" in result
        assert "経過" not in result

    def test_skips_age_when_current_tick_none(self) -> None:
        """current_tick=None なら age 計算をスキップし、tick part のみ。"""
        memo = _make_memo("m1", "メモ", added_at_tick=5)
        result = format_active_memos([memo], current_tick=None)
        assert "[tick=5]" in result
        assert "経過" not in result
        assert "[STALE]" not in result

    def test_renders_multiple_memos_separated_by_newline(self) -> None:
        """複数 memo は改行区切り。"""
        m1 = _make_memo("m1", "A", added_at_tick=0)
        m2 = _make_memo("m2", "B", added_at_tick=1)
        result = format_active_memos([m1, m2], current_tick=2)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "A" in lines[0]
        assert "B" in lines[1]
