"""作業記憶を、今のプロンプトの書き方の文にすることを保証する (design_decisions D1630-2)。"""

from __future__ import annotations

from ai_rpg_world.being.application.working_memory_text import (
    closing_text,
    message_text,
    section_text,
    system_prompt_text,
)
from ai_rpg_world.being.domain.working_memory import Closing, Section, Steadiness, WorkingMemory


def _section(heading: str | None, *lines: str, steadiness: Steadiness = Steadiness.EVERY_TURN) -> Section:
    return Section(heading=heading, lines=lines, steadiness=steadiness)


class TestSectionText:
    """区画 1 つを文にする書き方を保証する。"""

    def test_heading_is_bracketed_on_its_own_line(self) -> None:
        """見出しは【】で囲んで 1 行目に置き、本文の行が続く。"""
        assert section_text(_section("メモ", "やること:", "  (なし)")) == "【メモ】\nやること:\n  (なし)"

    def test_section_without_heading_is_only_its_lines(self) -> None:
        """見出しの無い区画は、本文の行だけになる。"""
        assert (
            section_text(_section(None, "あなたは次のペルソナとして行動する。"))
            == "あなたは次のペルソナとして行動する。"
        )


class TestWholeText:
    """システムプロンプトとメッセージの並べ方を保証する。"""

    def test_system_sections_are_separated_by_a_blank_line(self) -> None:
        """システムプロンプトの区画は、空行で区切って並ぶ。"""
        memory = WorkingMemory(
            system=(
                _section(None, "冒頭", steadiness=Steadiness.FIXED),
                _section("ペルソナ", "ハル", steadiness=Steadiness.ON_ENTRY),
            ),
            message=(),
        )

        assert system_prompt_text(memory) == "冒頭\n\n【ペルソナ】\nハル"

    def test_message_puts_warning_then_notices_then_the_closing(self) -> None:
        """メッセージは、区画、繰り返しの警告、知らせ、締めの一文の順に空行で区切って並ぶ。"""
        memory = WorkingMemory(
            system=(),
            message=(_section("現在地と周囲", "集会室"),),
            notices=(_section("時間の経過", "- 5 分"),),
            closing=Closing(instruction="行動を選ぶ。", warning="⚠ 同じ手が続いた。"),
        )

        assert (
            message_text(memory)
            == "【現在地と周囲】\n集会室\n\n⚠ 同じ手が続いた。\n\n【時間の経過】\n- 5 分\n\n行動を選ぶ。"
        )

    def test_message_without_warning_or_notices_ends_with_the_closing(self) -> None:
        """警告も知らせも無ければ、区画の後ろに締めの一文だけが続く。"""
        memory = WorkingMemory(
            system=(), message=(_section("現在地と周囲", "集会室"),), closing=Closing(instruction="行動を選ぶ。")
        )

        assert message_text(memory) == "【現在地と周囲】\n集会室\n\n行動を選ぶ。"

    def test_closing_text_is_the_part_after_the_sections(self) -> None:
        """区画より後ろの文 (警告、知らせ、締め) は、メッセージの末尾と同じ文になる。"""
        memory = WorkingMemory(
            system=(),
            message=(_section("現在地と周囲", "集会室"),),
            notices=(_section("時間の経過", "- 5 分"),),
            closing=Closing(instruction="行動を選ぶ。", warning="⚠ 同じ手が続いた。"),
        )

        assert closing_text(memory) == "⚠ 同じ手が続いた。\n\n【時間の経過】\n- 5 分\n\n行動を選ぶ。"
        assert message_text(memory).endswith("\n\n" + closing_text(memory))
