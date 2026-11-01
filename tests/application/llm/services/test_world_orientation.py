"""シナリオの世界に入るときの案内 (Orientation) を、今のシステムプロンプトの文から詰める規則を保証する (design_decisions D1630)。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.description_text import descriptions_text
from ai_rpg_world.application.llm.services.world_orientation import world_orientation
from ai_rpg_world.being.contract import Description


class TestWorldOrientation:
    """人柄・世界の前提・見取り図を、見出しの行で始まる段落ごとの説明文に分けることを保証する。"""

    def test_persona_comes_first_and_premise_holds_title_and_intro(self) -> None:
        """人柄が先頭に、舞台のタイトルと概要が【世界の前提】の文になる。"""
        orientation = world_orientation(persona_block="あなたはハル。", world_title="廃坑の山村", intro="雪の山村。")

        assert orientation.descriptions == (
            Description(heading="ペルソナ", text="あなたはハル。"),
            Description(heading="世界の前提", text="- 舞台のタイトル: 廃坑の山村\n- 概要: 雪の山村。"),
        )

    def test_persona_already_headed_loses_only_the_heading(self) -> None:
        """見出しの行から始まる構造化された人物像は、見出しを外した文になる。"""
        orientation = world_orientation(persona_block="【ペルソナ】\n- 名前: ハル", world_title="t", intro="i")

        assert orientation.descriptions[0] == Description(heading="ペルソナ", text="- 名前: ハル")

    def test_headed_paragraphs_become_their_own_descriptions(self) -> None:
        """概要と見取り図のうち、見出しの行で始まる段落はそれぞれ 1 つの説明文になる。"""
        orientation = world_orientation(
            persona_block="p",
            world_title="t",
            intro="吹雪。\n\n【このゲームについて】\n秘匿役職ゲーム。",
            briefing_sections=("【この場所の造り】\n  集会室 → 物資庫 まで 5 分",),
        )

        assert [d.heading for d in orientation.descriptions] == [
            "ペルソナ",
            "世界の前提",
            "このゲームについて",
            "この場所の造り",
        ]

    def test_paragraph_without_heading_continues_the_previous_description(self) -> None:
        """見出しの無い段落 (陣営の人数など) は、直前の説明文の文に空行を挟んで続く。"""
        orientation = world_orientation(
            persona_block="p",
            world_title="t",
            intro="吹雪。\n\n【このゲームについて】\n秘匿役職ゲーム。",
            briefing_sections=("参加者は 8 人。",),
        )

        assert orientation.descriptions[-1] == Description(
            heading="このゲームについて", text="秘匿役職ゲーム。\n\n参加者は 8 人。"
        )

    def test_heading_line_alone_continues_the_previous_description(self) -> None:
        """見出しの行だけで文の無い段落は、説明文にせず直前の説明文に続ける。"""
        orientation = world_orientation(persona_block="p", world_title="t", intro="吹雪。\n\n【このゲームについて】")

        assert orientation.descriptions[-1] == Description(
            heading="世界の前提", text="- 舞台のタイトル: t\n- 概要: 吹雪。\n\n【このゲームについて】"
        )

    def test_rules_come_last_without_touching_the_briefing(self) -> None:
        """この世界の決まりは見取り図の後ろに別の説明文として付き、見取り図の文は変えない。無ければ付かない。"""
        rules = Description(heading="この世界の決まり", text="- 行動の制限: 限りがある")
        with_rules = world_orientation(
            persona_block="p",
            world_title="t",
            intro="i",
            briefing_sections=("【決まり】\n- 棄権も 1 票",),
            rules=rules,
        )
        without_rules = world_orientation(
            persona_block="p", world_title="t", intro="i", briefing_sections=("【決まり】\n- 棄権も 1 票",)
        )

        assert with_rules.descriptions[-2:] == (Description(heading="決まり", text="- 棄権も 1 票"), rules)
        assert without_rules.descriptions[-1] == Description(heading="決まり", text="- 棄権も 1 票")

    def test_text_reads_back_as_the_original_paragraphs(self) -> None:
        """説明文を見出しの行と空行で文に戻すと、人柄と世界の前提の元の文に一致する。"""
        intro = "吹雪。\n\n\n【このゲームについて】\n秘匿役職ゲーム。"
        orientation = world_orientation(
            persona_block="p", world_title="t", intro=intro, briefing_sections=("参加者は 8 人。",)
        )

        assert descriptions_text(orientation.descriptions) == (
            f"【ペルソナ】\np\n\n【世界の前提】\n- 舞台のタイトル: t\n- 概要: {intro}\n\n参加者は 8 人。"
        )
