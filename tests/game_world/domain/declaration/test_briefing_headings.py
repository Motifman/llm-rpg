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
    text=DescriptionText("冬が近い山あいの廃村。"),
    premises=DescriptionText("昇降機は一度しか動かない。"),
    shows_world_map=False,
)
_MAP = "  井戸 (明るい) → 広場 まで 30 分"

_HEADINGS = {
    "introduction": "この世界について",
    "premises": "この世界の前提",
    "world_map": "この場所の造り",
}
_PAIRS = [(first, second) for i, first in enumerate(_HEADINGS) for second in tuple(_HEADINGS)[i + 1 :]]


class TestBriefingHeadings:
    """BriefingHeadings が、導入・前提・地図を見出しの違う説明にし、使えない見出しを宣言のときに断ることを保証する。"""

    def test_orientation_lists_introduction_premises_and_map_in_order(self) -> None:
        """案内には、導入・前提・地図が、それぞれの見出しでこの順に並ぶ。この世界で知っていることは入らない (D2267)。"""
        headings = BriefingHeadings(**_HEADINGS)

        orientation = headings.orientation(_INTRODUCTION, _MAP)

        assert tuple(orientation.descriptions) == (
            Description(heading="この世界について", text="冬が近い山あいの廃村。"),
            Description(heading="この世界の前提", text="昇降機は一度しか動かない。"),
            Description(heading="この場所の造り", text=_MAP),
        )

    def test_orientation_without_a_map_has_no_map_heading(self) -> None:
        """地図を渡さないと、案内は導入・前提の 2 つだけになる。"""
        headings = BriefingHeadings(**_HEADINGS)

        orientation = headings.orientation(_INTRODUCTION, None)

        assert [d.heading for d in orientation.descriptions] == ["この世界について", "この世界の前提"]

    @pytest.mark.parametrize("field", list(_HEADINGS))
    @pytest.mark.parametrize("heading", ["", "  ", "【前提】", "この世界の\n前提"])
    def test_malformed_heading_is_refused(self, field: str, heading: str) -> None:
        """どの欄でも、空白だけ・【】を含む・2 行にわたる見出しは MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            BriefingHeadings(**{**_HEADINGS, field: heading})

    @pytest.mark.parametrize(
        ("first", "second"),
        _PAIRS,
    )
    def test_repeated_heading_is_refused(self, first: str, second: str) -> None:
        """どの 2 つの見出しが同じでも RepeatedBriefingHeadingException で断る。案内は見出しの重なりを許さないため。"""
        with pytest.raises(RepeatedBriefingHeadingException):
            BriefingHeadings(**{**_HEADINGS, second: _HEADINGS[first]})
