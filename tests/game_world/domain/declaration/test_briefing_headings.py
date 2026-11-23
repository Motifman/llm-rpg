from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.exception.briefing_headings_exception import MalformedBriefingHeadingException
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName
from tests.game_world.support.world_design_for_tests import briefing_headings

_INTRODUCTION = WorldIntroduction(
    title=DisplayName("廃坑の山村"),
    text=DescriptionText("冬が近い山あいの廃村。\n\n坑道の中は光が無いと何も見えない。"),
    premises=DescriptionText("- 昇降機は一度しか動かない。"),
    shows_world_map=False,
)
_MAP = "  井戸 (明るい) → 広場 まで 30 分"
_TITLE_AND_OVERVIEW = (
    "- 舞台のタイトル: 廃坑の山村",
    "- 概要: 冬が近い山あいの廃村。",
    "",
    "坑道の中は光が無いと何も見えない。",
)


def _premises(introduction: WorldIntroduction, world_map: str | None, has_deadline: bool) -> object:
    premises, _ = briefing_headings().orientation(introduction, world_map, has_deadline).descriptions
    assert premises.heading == "世界の前提"
    return premises.text


class TestOrientation:
    """BriefingHeadings.orientation が、古い run の【世界の前提】の並びで題名・概要・前提・地図・行動の制限を 1 つの説明にすることを保証する。"""

    def test_title_overview_premises_map_and_deadline_in_the_old_order(self) -> None:
        """題名、概要 (段落ごと)、前提の行、空行のあとの地図の見出しと地図、行動の制限の順に並ぶ。"""
        assert _premises(_INTRODUCTION, _MAP, has_deadline=True) == "\n".join(
            (
                *_TITLE_AND_OVERVIEW,
                "- 昇降機は一度しか動かない。",
                "",
                "【この場所の造り】",
                _MAP,
                "- 行動の制限: 行動の総量には限りがある。",
            )
        )

    def test_world_without_premises_map_or_deadline_has_title_and_overview_only(self) -> None:
        """前提の欄が空で、地図を見せず、締め切りの無い世界は、題名と概要だけになる。"""
        introduction = dataclasses.replace(_INTRODUCTION, premises=None)

        assert _premises(introduction, None, has_deadline=False) == "\n".join(_TITLE_AND_OVERVIEW)


class TestWorldRules:
    """BriefingHeadings.orientation が、世界の前提のあとに【この世界の決まり】を 2 つ目の説明として渡すことを保証する。"""

    def test_rules_follow_the_premises_as_their_own_description(self) -> None:
        """案内は「世界の前提」「この世界の決まり」の順の 2 つで、決まりの本文は決まりの行をそのまま並べたもの。"""
        premises, rules = briefing_headings().orientation(_INTRODUCTION, None, has_deadline=False).descriptions

        assert (premises.heading, rules.heading, rules.text) == (
            "世界の前提",
            "この世界の決まり",
            "- ラベルは表示されたものだけを使う。",
        )

    @pytest.mark.parametrize("lines", [(), ("",), ("- 一つ目\n- 二つ目",)])
    def test_empty_or_blank_rule_lines_are_refused(self, lines: tuple[str, ...]) -> None:
        """決まりの行が 1 つも無い、または空の行を含むと、MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            dataclasses.replace(briefing_headings(), rule_lines=lines)


class TestBriefingHeadings:
    """BriefingHeadings が、使えない見出しと言い回しを宣言のときに断ることを保証する。"""

    @pytest.mark.parametrize("heading", ["", "  ", "【前提】", "この世界の\n前提"])
    def test_malformed_heading_is_refused(self, heading: str) -> None:
        """空白だけ・【】を含む・2 行にわたる見出しは MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            dataclasses.replace(briefing_headings(), premises=heading)

    @pytest.mark.parametrize("heading", ["", "【決まり】"])
    def test_malformed_rules_heading_is_refused(self, heading: str) -> None:
        """決まりの見出しも、空や【】を含むものは MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            dataclasses.replace(briefing_headings(), rules=heading)

    @pytest.mark.parametrize(("field", "text"), [("title", "- 舞台のタイトル"), ("overview", "- 概要: {title}")])
    def test_line_that_does_not_write_its_value_is_refused(self, field: str, text: str) -> None:
        """題名を書かない題名の行や、概要の代わりに別の値を書く概要の行は、MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            dataclasses.replace(briefing_headings(), **{field: text})

    @pytest.mark.parametrize("field", ["world_map", "deadline"])
    def test_blank_line_is_refused(self, field: str) -> None:
        """地図の見出しや行動の制限の文が空白だけだと、MalformedBriefingHeadingException で断る。"""
        with pytest.raises(MalformedBriefingHeadingException):
            dataclasses.replace(briefing_headings(), **{field: " "})
