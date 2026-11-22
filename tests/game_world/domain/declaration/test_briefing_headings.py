from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import Description
from ai_rpg_world.game_world.domain.declaration.briefing_headings import BriefingHeadings
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.exception.briefing_headings_exception import (
    MalformedBriefingHeadingException,
    RepeatedBriefingHeadingException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText

_INTRODUCTION = WorldIntroduction(
    text=DescriptionText("冬が近い山あいの廃村。"), premises=DescriptionText("昇降機は一度しか動かない。")
)


class TestBriefingHeadings:
    """BriefingHeadings が、導入・前提・知っていることを見出しの違う 3 つの説明にし、使えない見出しを宣言のときに断ることを保証する。"""

    def test_orientation_lists_introduction_premises_and_known_facts_in_order(self) -> None:
        """案内には、導入・前提・知っていることが、それぞれの見出しでこの順に並ぶ。"""
        headings = BriefingHeadings(
            introduction="この世界について", premises="この世界の前提", known_facts="あなたが知っていること"
        )

        orientation = headings.orientation(_INTRODUCTION, DescriptionText("金庫の番号は 1907。"))

        assert tuple(orientation.descriptions) == (
            Description(heading="この世界について", text="冬が近い山あいの廃村。"),
            Description(heading="この世界の前提", text="昇降機は一度しか動かない。"),
            Description(heading="あなたが知っていること", text="金庫の番号は 1907。"),
        )

    @pytest.mark.parametrize("heading", ["", "  ", "【前提】", "この世界の\n前提"])
    def test_malformed_heading_is_refused(self, heading: str) -> None:
        """空白だけ・【】を含む・2 行にわたる見出しは MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            BriefingHeadings(introduction="この世界について", premises=heading, known_facts="あなたが知っていること")

    def test_repeated_heading_is_refused(self) -> None:
        """2 つの見出しが同じなら RepeatedBriefingHeadingException で断る。案内は見出しの重なりを許さないため。"""
        with pytest.raises(RepeatedBriefingHeadingException):
            BriefingHeadings(
                introduction="この世界について", premises="この世界について", known_facts="あなたが知っていること"
            )
