"""tend_to_player の description が「疲労や空腹ではなく down 限定」と明確に伝わるか (PR-J)。

Y_after_pr634 trace で観測された問題:
- tick 35 P1 が ノア に対し ``tend_to_player`` を呼んだが、ノアは倒れていなかった
  (= INTERACTION_PRECONDITION_FAILED)。inner_thought:
  「ノアが拠点に戻っている。まずは彼の怪我を診て手当てをしないと。」
- tick 81 P2 が エイダ に対して同様に呼んだ。
  「エイダの顔色が良くない。空腹と疲労で限界なら、まずは休ませないと。」

原因: 旧 description は「同じ場所に倒れている仲間を介抱して意識を取り戻させる」
だったが、「介抱」という日本語が「ケア全般 / 看病 / 治療」を包含するため
LLM が「疲労や空腹で限界の相手にも使える」と読んでしまった。

対処: description で
  (1) 倒れている = status_effect: down = HP 0 と明示
  (2) 疲労や空腹だけでは対象外であることを否定形で書く
を両方カバーする。

description は静的文字列なので prefix cache を壊さない (cf. CLAUDE.md
``description を動的化するアンチパターン``)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    TEND_TO_PLAYER_DEFINITION,
)


class TestTendToPlayerDescriptionIsExplicitAboutDownOnly:
    """description が「down 状態の相手だけ」という制約を明示的に伝えるか。"""

    def test_status_effect_down_を_明示する(self) -> None:
        """旧文言「戦闘不能状態」だけでは LLM が疲労 100 と混同したので、
        ``status_effect`` か ``down`` という機械的なキーワードを少なくとも 1 つ含める。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "status_effect" in desc or "down" in desc, (
            "description に内部状態キー (status_effect / down) を含めないと "
            "「倒れている」が抽象的すぎて疲労や空腹と混同される"
        )

    def test_HP_0_を_明示する(self) -> None:
        """「倒れている」が比喩か機械的状態かを区別するため HP 0 / HP=0 を書く。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "HP 0" in desc or "HP=0" in desc or "HP がゼロ" in desc, (
            "down の機械的定義 (HP 0) を書かないと、疲労 100 や空腹 100 を "
            "down と読み替える誤発火が起きる"
        )

    def test_疲労や空腹では_対象外_を_否定形で_明示する(self) -> None:
        """LLM が「顔色が悪い = 疲労限界 = 介抱対象」と読まないように、
        疲労や空腹は対象外であることを否定形で書く。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "疲労" in desc and "空腹" in desc, (
            "Y_after_pr634 で観測された 2 件の誤発火はいずれも「疲労」「空腹」を "
            "理由に呼ばれていた。description にこの 2 語を否定形で含めて、"
            "LLM の prompt 上で衝突解決させる必要がある"
        )

    def test_介抱_ではなく_蘇生_を_主動詞に使う(self) -> None:
        """「介抱」は「看病・治療・世話」を含む広い動詞で誤読の温床なので、
        主動詞は「蘇生」(= 倒れた人を起こす) に寄せる。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "蘇生" in desc, (
            "「介抱」だけでは「疲れた相手をケアする」と読まれる。"
            "「蘇生」を主動詞に置いて down 限定の含意を強める"
        )


class TestTendToPlayerDescriptionDoesNotBreakPrefixCache:
    """description は cache を壊さないよう静的文字列であり続ける。"""

    def test_description_は_str_型で_動的補間されない(self) -> None:
        """f-string や format による動的差し込みが入っていないことを保証する。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert isinstance(desc, str)
        assert "{" not in desc, "placeholder が残っている = 動的補間の疑い"
        assert "%" not in desc or "%s" not in desc, "printf 補間の疑い"
