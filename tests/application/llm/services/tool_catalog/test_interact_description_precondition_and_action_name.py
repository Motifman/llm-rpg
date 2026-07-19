"""``spot_graph_interact`` の description が precondition と action_name の
正しい使い方を伝えるか (案 4 / Y_after_pr634 後続)。

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
2. **action_name の例示ゼロ**。「オブジェクトに定義された action_name」と
   トートロジーで、LLM が日本語化推測する
3. **「現在の状況」section との対応が暗黙**

本 PR では description を以下の方針で書き直す:

- precondition の存在を明示し、満たさない場合は ``INTERACTION_PRECONDITION_FAILED``
  で失敗することを書く
- action_name に具体例 (``gather`` / ``search`` / ``examine``) を示し、
  日本語や敬体ではなく英語の動詞形を渡すこと、推測せず prompt の
  「現在の状況」から読み取ることを書く

description は静的文字列 (prefix cache 安全)。CLAUDE.md の
「description 動的化はアンチパターン」に沿う。
"""

from __future__ import annotations

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


class TestInteractActionNameDescriptionGivesConcreteExamples:
    """action_name の description に具体例と「推測禁止」が入る。"""

    def test_includes_action_name_three(self) -> None:
        """``gather`` / ``search`` / ``examine`` のような典型 action 名を
        例示することで、日本語化 (「調べる」「採取」) を防ぐ。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        examples_present = sum(
            ex in action_name_desc
            for ex in ("gather", "search", "examine")
        )
        assert examples_present >= 3, (
            "3 個の英語 action 名を例示しないと、LLM は単独例を見て同種を "
            "推測しがち。3 個並べることで「英語の動詞形」というパターンが "
            "伝わる"
        )

    def test_includes_japanese_english(self) -> None:
        """LLM が ``action_name='調べる'`` のような日本語値を渡す事故を
        明示的に潰す。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        assert (
            "日本語" in action_name_desc or "英語" in action_name_desc
        ), "「英語の動詞形」「日本語ではなく」のような禁止文がないと "
        "Y_after_pr634 で観測された日本語 action_name 事故が再現する"

    def test_includes(self) -> None:
        """「思いつきで推測せず、必ず『現在の状況』から読み取る」という
        指示が含まれる。"""
        action_name_desc = INTERACT_DEFINITION.parameters["properties"]["action_name"][
            "description"
        ]
        assert "推測" in action_name_desc, (
            "「推測」という語を含めないと、LLM の即興発明 (例: \"探索\" "
            "\"採取\") を直接潰せない"
        )


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
