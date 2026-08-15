"""全ツールに複製される 2 つの説明が、短くしても何も落としていないことを見る。

## なぜこの試験が要るか

`inner_thought` と `say_inline` の説明は**全ツールの schema に複製される**
(27 ツール / 21 ツール)。**1 文字が 27 文字になる**ので、ここを縮めると効きやすい。

だからこそ危ない。**削減作業でいちばん危ないのは、削った本人が気づかない欠落**
である。実際この作業で「確認」という発話の種類を 1 つ落としかけた (レビューで
差し戻された。相談は答えを求める、確認は合っているかを問う、で別の行為である)。

## 何を守るか

**言い回しは削ってよい。制約と種類は削ってはいけない。**

- 質感の制約 (演技にしない / 未発見の事実を知った体で書かない) — 消すと独白が
  語りになり、知らないはずのことを知っている風に書き始める
- 発話の種類 (報告・相談・呼びかけ・確認) — 消すとその種類の発話が起きなくなる
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.inner_thought import (
    INNER_THOUGHT_DEFAULT_DESCRIPTION,
)
from ai_rpg_world.application.llm.services.tool_catalog.say_inline import (
    SAY_INLINE_DEFAULT_DESCRIPTION,
)

#: 独白の説明から消してはいけないもの。
_INNER_THOUGHT_MUST_KEEP = (
    "ペルソナ",              # 口調を揃える相手
    "独白",                  # 何を書くのか
    "演技",                  # 見せるための語りにしない
    "情景描写",
    "未発見の事実",          # 知らないことを知っている風に書かない
)

#: 一言の説明から消してはいけないもの。**発話の種類は数を減らさない。**
_SAY_INLINE_MUST_KEEP = (
    "200 字以内",
    "隣",                    # 届く範囲
    "報告",
    "相談",
    "呼びかけ",
    "確認",
    "発話専用のターン",      # 使わずに済むという指示
    "空なら発話しない",
)


class TestTheInnerThoughtRulesAllSurvive:
    """独白の制約が、短くしても全部残っている。"""

    @pytest.mark.parametrize("rule", _INNER_THOUGHT_MUST_KEEP)
    def test_the_rule_is_still_there(self, rule: str) -> None:
        """制約が 1 つも消えていない。

        **消すと、この実験が見たいものそのものが壊れる。**
        """
        assert rule in INNER_THOUGHT_DEFAULT_DESCRIPTION


class TestEveryKindOfSpeechSurvives:
    """一言の説明から、発話の種類が減っていない。"""

    @pytest.mark.parametrize("kind", _SAY_INLINE_MUST_KEEP)
    def test_the_kind_is_still_there(self, kind: str) -> None:
        """種類が 1 つも消えていない。

        **数文字を惜しんで種類を減らすと、その種類の発話が起きなくなる。**
        実際この作業で「確認」を落としかけた。
        """
        assert kind in SAY_INLINE_DEFAULT_DESCRIPTION


class TestTheWordingActuallyGotShorter:
    """縮めた結果が、実際に短くなっている (**正の対照**)。

    これが無いと、上の 2 つは「1 文字も変えていない」でも緑になる。
    """

    def test_both_are_under_their_previous_length(self) -> None:
        """どちらも、縮める前の長さより短い。

        縮める前: 独白 170 文字 / 一言 148 文字 (本文のみ)。
        """
        assert len(INNER_THOUGHT_DEFAULT_DESCRIPTION) < 170
        assert len(SAY_INLINE_DEFAULT_DESCRIPTION) < 148
