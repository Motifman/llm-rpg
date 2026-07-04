"""``spot_graph_tend_to_player`` の description から内部技術用語を排除する
(Y_after_pr639_640_200tick 後続、E-36 の観測より)。

Y_after_pr639_640 の分析で TEND_TO_PLAYER_DEFINITION.description に
``status_effect: down`` という内部フィールド名がそのまま LLM に露出している
ことが判明した。LLM は重みの学習をしていないので (in-context のみ)、
この生の技術用語を見せる意味は無く、LLM に馴染む日本語ラベル (「ダウン状態」
「HP 0 で倒れている」) だけで十分に区別できる。

**変更点**:
- ``status_effect: down`` を「ダウン状態」に置換
- ``HP 0`` はそのまま (数値表現はゲーム内 UI と一致するので LLM も理解しやすい)
- 他内容 (前提条件、疲労・空腹との違い、自分自身の除外) はそのまま保持

description は静的文字列 (prefix cache 安全)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    TEND_TO_PLAYER_DEFINITION,
)


class TestTendToPlayerDescriptionNoInternalJargon:
    """内部フィールド名 (``status_effect`` 等) が LLM 露出テキストに漏れない。"""

    def test_status_effect_という語が_含まれない(self) -> None:
        """内部フィールド名を LLM に見せない。ダウン状態は日本語表記で十分。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "status_effect" not in desc, (
            "内部技術用語 'status_effect' が LLM 露出テキストに残っている。"
            "「ダウン状態」等の日本語表記に置換すべき"
        )

    def test_ダウン_という語で対象状態が示される(self) -> None:
        """状態タグとして日本語の『ダウン』が使われている。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "ダウン" in desc, (
            "『ダウン』という状態表現が description に無いと、"
            "LLM は対象状態を正しく識別できない"
        )

    def test_HP_0_の記載は保持される(self) -> None:
        """HP 数値表現は LLM に分かりやすいので保持する (UI と一致)。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "HP 0" in desc, "HP 0 は具体的な失敗条件なので description に残す"

    def test_疲労や空腹では対象外_の否定形が残る(self) -> None:
        """PR #636 で入れた「疲労・空腹では tend できない」文言が残っている。"""
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert "疲労" in desc and "空腹" in desc, (
            "PR #636 で入れた疲労・空腹除外の記述が消えていないこと"
        )

    def test_description_は_str_型で_placeholder_なし(self) -> None:
        desc = TEND_TO_PLAYER_DEFINITION.description
        assert isinstance(desc, str)
        assert "{" not in desc, "placeholder の疑い"
