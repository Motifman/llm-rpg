"""発話の履歴に、意味のない呼び出し行が付かないことを保証する。

## なぜこの試験が要るか

自分の行動は履歴に 3 行で残る。

    - [深夜 5:05] [行動] あなたは言った: 「…」（2 名に届いた）
      呼び出し: speak(channel="say", content=本文)      ← この行
      心の声: …

**本文は伏せ字になる**ので、この行は `speak(content=本文)` としか書けない。
直前の行が「あなたは言った」と言っている以上、**情報が 1 文字も増えない**。
手本としても働かない (**伏せ字を真似しても意味がない**)。

実測で 1 手番あたり 136 文字、run 全体では無視できない量になる。

## 他のツールでは残す

`interact(action_name="bake_bread", target_label="石窯")` のように、**引数が
具体値**のものは「次に同じ呼び方をする」手本になる。**落とすと失敗が増えるかも
しれない**ので、いちばん無意味な 1 種類だけを消す。
"""

from __future__ import annotations

import pytest

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    format_action_result_line_for_recent_events,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry


def _line(tool_name: str, **kwargs) -> str:
    entry = ActionResultEntry(
        occurred_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        tool_name=tool_name,
        action_summary=kwargs.pop("action_summary", "あなたは言った: 「やあ」"),
        result_summary=kwargs.pop("result_summary", "（2 名に届いた）"),
        success=True,
        identifier_arguments=kwargs.pop("identifier_arguments", {}),
        free_text_argument_names=kwargs.pop("free_text_argument_names", ("content",)),
        inner_thought=kwargs.pop("inner_thought", "話しかけよう。"),
        **kwargs,
    )
    return format_action_result_line_for_recent_events(entry)


class TestSpeakingLosesTheEmptyCallLine:
    """発話には呼び出し行が付かない。"""

    def test_no_call_line_for_speaking(self) -> None:
        """`speak` の行に「呼び出し:」が出ない。"""
        assert "呼び出し:" not in _line("speak")

    def test_what_was_said_is_still_there(self) -> None:
        """発話そのものは残る (**正の対照**)。

        行ごと消すと、何を言ったかが履歴から消える。
        """
        line = _line("speak")

        assert "あなたは言った" in line
        assert "（2 名に届いた）" in line

    def test_the_inner_voice_is_still_there(self) -> None:
        """心の声も残る。

        **自分の過去の判断が自分に見えなくなる**のは別の問題なので、
        ここでは触らない。
        """
        assert "心の声: 話しかけよう。" in _line("speak")


class TestOtherToolsKeepTheirCallLine:
    """他のツールの呼び出し行は残る。"""

    def test_a_tool_with_real_arguments_keeps_it(self) -> None:
        """引数が具体値のツールは、呼び出し行を保つ。

        **落とすと「次に同じ呼び方をする」手本が消える。** いちばん無意味な
        1 種類だけを消す、という線引き。
        """
        line = _line(
            "interact",
            action_summary='「石窯」でパンを焼く',
            result_summary="焼きたてのパンがふたつできた。",
            identifier_arguments={"action_name": "bake_bread", "target_label": "石窯"},
            free_text_argument_names=(),
        )

        assert "呼び出し: interact(" in line
        assert "bake_bread" in line
