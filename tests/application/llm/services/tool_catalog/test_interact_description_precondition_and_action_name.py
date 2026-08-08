"""``spot_graph_interact`` が、実在する値の読み方だけを伝える。

Y_after_pr634 trace で観測された問題:
- ``INTERACTION_PRECONDITION_FAILED`` 24 件 (baseline 3 件、+700%)。大半は
  「流木の山 gather」「漂着物 search_debris」の連発で、一度成功すると
  ``available=false`` / ``opened=true`` になることを LLM が知らずに繰り返した
- ``INTERACTION_ACTION_NOT_FOUND`` の残 1 件 (t13 P4) は ``action_name='調べる'``
  と日本語化したもの。英語 action_name の存在を LLM が認識していなかった

旧 description (60 字):

> 「現在のスポット内のオブジェクトに対し、指定した操作名で相互作用する。
>  パズル操作の場合はparametersに入力値を指定する。」

問題点:

1. **precondition の概念が完全に欠落**。「action が存在 = 呼べば成功」と読まれる
2. **action_name の読み方が無い**。LLM が表示名や推測名を渡す
3. **「現在の状況」section との対応が暗黙**

本 PR では description を以下の方針で書き直す:

- precondition の存在を明示し、満たさない場合は ``INTERACTION_PRECONDITION_FAILED``
  で失敗することを書く
- action_name は「現在の状況」の対象行から読み取ると書く
- シナリオに存在するとは限らない具体名を、静的な手本として載せない

description は静的文字列 (prefix cache 安全)。CLAUDE.md の
「description 動的化はアンチパターン」に沿う。
"""

from __future__ import annotations

import re

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    INTERACT_DEFINITION,
)


class TestInteractTopLevelDescriptionExplainsPrecondition:
    """top-level description が「前提条件で失敗しうる」概念を伝える。"""

    def test_includes_before_precondition(self) -> None:
        """「action が存在 = 呼べば成功」誤読を防ぐため、前提という概念を
        日本語または英語キーワードで明示する。"""
        desc = INTERACT_DEFINITION.description
        assert "前提" in desc or "precondition" in desc, (
            "前提条件の存在を伝えないと、流木の山 gather 4 連発のような "
            "PRECONDITION_FAILED の繰り返しが止まらない"
        )

    def test_interaction_precondition_failed(self) -> None:
        """失敗時に観測される error_code を description に書き、LLM が
        失敗ログを見たときに「これは前提不足だ」と即時判断できるようにする。"""
        desc = INTERACT_DEFINITION.description
        assert "INTERACTION_PRECONDITION_FAILED" in desc, (
            "error_code 名を含めると、失敗を見た LLM が原因と結びつけられる"
        )

    def test_includes_section(self) -> None:
        """precondition と action 一覧は『現在の状況』section に出ているので、
        そこを読めば良いという誘導文を入れる。"""
        desc = INTERACT_DEFINITION.description
        assert "現在の状況" in desc, (
            "precondition と action_name の出所を明示しないと、LLM が "
            "思いつきで推測してしまう"
        )


class TestInteractActionNameDescriptionUsesOnlyOfferedValues:
    """action_name は現在状況の引用値から選ばせる。"""

    def test_concrete_action_names_are_not_advertised(self) -> None:
        """静的な説明は、存在しない操作名を写せる手本にしない。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        identifiers = set(re.findall(r"[a-z][a-z0-9_]*", action_name_desc))
        assert identifiers == {"action_name"}
        assert "例" not in action_name_desc

    def test_points_to_the_quoted_value_in_current_state(self) -> None:
        """実在する値の出所と、そのまま写す規則を明示する。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        assert "現在の状況" in action_name_desc
        assert '``\"\"``' in action_name_desc
        assert "そのまま" in action_name_desc
        assert "推測" in action_name_desc, (
            "表示に無い値の即興発明を直接禁じる必要がある"
        )


class TestInteractTargetDescriptionDoesNotInventAnActionExample:
    """対象名の説明も、操作名の偽の手本を含まない。"""

    def test_target_description_uses_the_current_row_without_an_example(self) -> None:
        """対象行の読み方だけを示し、固定の対象や操作は示さない。"""
        target_desc = INTERACT_DEFINITION.parameters["properties"]["target_label"][
            "description"
        ]
        assert "現在の状況" in target_desc
        assert '``\"\"``' in target_desc
        assert "例" not in target_desc
        assert not any(name in target_desc for name in ("gather", "search", "examine"))


class TestInteractDescriptionDoesNotBreakPrefixCache:
    """description / action_name は静的文字列を保つ (= cache 安全)。"""

    def test_top_description_string(self) -> None:
        """topdescription は静的文字列。"""
        desc = INTERACT_DEFINITION.description
        assert isinstance(desc, str)
        assert "{" not in desc, "placeholder の疑い"

    def test_action_name_description_string(self) -> None:
        """actionnamedescription は静的文字列。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        assert isinstance(action_name_desc, str)
        assert "{" not in action_name_desc, "placeholder の疑い"
