"""ツールの説明文が、この世界に無いツールの名前を勧めない。

説明文の中には、ほかのツールに触れる文がある (「同じ場所の相手に渡すには give_item を
使う」など)。勧めた先のツールが無効化された世界では、その文は打てない手を勧める。
説明文を LLM に渡す前に、無いツールに触れる文を外す (CLAUDE.md の「プロンプト本文に
ツール名を書くときは、必ず露出判断を通すこと」)。
"""

from __future__ import annotations

import re

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.cross_tool_mentions import (
    CROSS_TOOL_MENTIONS,
    without_absent_tool_mentions,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs

_DEFINITIONS = [definition for definition, _ in get_spot_graph_specs()]
_NAMES = sorted(definition.name for definition in _DEFINITIONS)


def _names_in(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z_]){re.escape(name)}(?![A-Za-z_])", text) is not None


class TestMentionsOfAbsentToolsAreRemoved:
    """勧めた先のツールが無い世界では、そのツールに触れる文が説明文から外れることを保証する。"""

    @pytest.mark.parametrize("absent", _NAMES)
    def test_no_description_names_the_absent_tool(self, absent: str) -> None:
        """ツールを 1 つ無いことにすると、ほかのどのツールの説明文にもその名前が残らない。"""
        offenders = [
            definition.name
            for definition in _DEFINITIONS
            if definition.name != absent
            and _names_in(
                without_absent_tool_mentions(definition, lambda name: name != absent).description,
                absent,
            )
        ]

        assert offenders == []

    def test_descriptions_are_unchanged_when_every_tool_is_present(self) -> None:
        """すべてのツールが在る世界では、説明文はそのまま渡る。"""
        for definition in _DEFINITIONS:
            assert without_absent_tool_mentions(definition, lambda name: True) == definition

    def test_tend_to_player_still_suggests_food_without_speak(self) -> None:
        """話すツールが無い世界でも、介抱の説明は「食料を与える」という手を残す。"""
        tend = next(d for d in _DEFINITIONS if d.name == "tend_to_player")

        description = without_absent_tool_mentions(tend, lambda name: name != "speak").description

        assert "そうした相手には食料を与えること。" in description
        assert "speak" not in description


class TestTheMentionTableStaysTrue:
    """外す文の表が、説明文の本文とずれないことを保証する。"""

    def test_every_listed_sentence_is_in_its_description(self) -> None:
        """表に載せた文は、どれもそのツールの説明文に実在する (文面を変えたのに表を直し忘れると、外れずに残る)。"""
        by_name = {definition.name: definition for definition in _DEFINITIONS}
        missing = [
            (tool, sentence)
            for tool, mentions in CROSS_TOOL_MENTIONS.items()
            for _, sentence, _ in mentions
            if sentence not in by_name[tool].description
        ]

        assert missing == []

    def test_the_table_has_something_to_check(self) -> None:
        """表は空ではない (空を全部通ったと読まない)。"""
        assert sum(len(mentions) for mentions in CROSS_TOOL_MENTIONS.values()) >= 10
