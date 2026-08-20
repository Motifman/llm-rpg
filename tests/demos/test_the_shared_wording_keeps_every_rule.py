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
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)


def _everything_the_model_reads() -> str:
    """モデルが読むもの全部 (system prompt + 引数の説明)。

    **きまりがどこに書いてあるかは問題ではない。届いているかが問題。** 説明を
    system prompt へ寄せたので、schema だけを見る検査は「消えた」と誤判定する。
    """
    system = build_world_system_prompt(
        world_title="町",
        persona_block="【ペルソナ】あなたは焼き手だ。",
        safe_intro="市場のある町。",
        participant_names=("レナ",),
    )
    return system + INNER_THOUGHT_DEFAULT_DESCRIPTION + SAY_INLINE_DEFAULT_DESCRIPTION

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
        assert rule in _everything_the_model_reads()


class TestEveryKindOfSpeechSurvives:
    """一言の説明から、発話の種類が減っていない。"""

    @pytest.mark.parametrize("kind", _SAY_INLINE_MUST_KEEP)
    def test_the_kind_is_still_there(self, kind: str) -> None:
        """種類が 1 つも消えていない。

        **数文字を惜しんで種類を減らすと、その種類の発話が起きなくなる。**
        実際この作業で「確認」を落としかけた。
        """
        assert kind in _everything_the_model_reads()


class TestEachToolPointsAtTheSharedRules:
    """引数の説明は、要点を残したうえで共有の節を指す。"""

    def test_the_pointer_is_there(self) -> None:
        """どちらの説明も、共有の節を名指しする。

        **純粋な指し示しにはしない。** 参照が効かなかったときのために、
        「何を書く引数か」の一文は残す (下の検査)。
        """
        for text in (INNER_THOUGHT_DEFAULT_DESCRIPTION, SAY_INLINE_DEFAULT_DESCRIPTION):
            assert "【独白と一言の書き方】" in text

    def test_the_gist_survives_without_following_the_pointer(self) -> None:
        """参照を辿らなくても、何を書く引数かは分かる。

        指し示しだけにすると、**参照が効かないモデルには何も残らない**。
        """
        # **参照そのものを要点と数えない。** 「書き方は【独白と一言の書き方】」に
        # 「独白」「一言」が含まれるので、その語だけを見ると**指し示しだけに
        # しても通る** (変異で実際に生き残った)。参照を取り除いた残りを見る。
        pointer = "書き方は【独白と一言の書き方】。"
        gist = {
            "独白": INNER_THOUGHT_DEFAULT_DESCRIPTION.replace(pointer, ""),
            "一言": SAY_INLINE_DEFAULT_DESCRIPTION.replace(pointer, ""),
        }
        for word, text in gist.items():
            assert word in text, text

    def test_the_shared_block_is_conditional(self) -> None:
        """共有の節は「その引数を持つツールでは」と条件つきで書かれている。

        無条件に「独白を必ず書け」と書くと、**引数を持たないツールで矛盾**する。
        """
        system = _everything_the_model_reads()

        assert "`inner_thought` を持つツールでは" in system
        assert "`say_inline` を持つツールでは" in system


class TestTheWordingActuallyGotShorter:
    """縮めた結果が、実際に短くなっている (**正の対照**)。

    これが無いと、上の 2 つは「1 文字も変えていない」でも緑になる。
    """

    def test_both_stay_within_the_budget(self) -> None:
        """どちらも、決めた長さに収まっている。

        縮める前は 独白 141 文字 / 一言 134 文字 (本文のみ)。上限を「縮める前」に
        置くと**ほとんど縮めなくても通る**ので、縮めた後の値に近いところへ置く。

        最初はここを「縮める前より短い」にしていて、**変異 (何も縮めない) が
        生き残った**。上限の置き方そのものが空振りしていた。
        """
        assert len(INNER_THOUGHT_DEFAULT_DESCRIPTION) <= 60
        assert len(SAY_INLINE_DEFAULT_DESCRIPTION) <= 60
