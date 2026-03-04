"""tool_constants（プレフィックス・ツール名定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_PREFIXES,
    TOOL_NAME_PREFIX_DESCRIPTIONS,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_NO_OP,
)


class TestToolNamePrefixes:
    """プレフィックス定数の一貫性"""

    def test_prefixes_list_contains_expected(self):
        """TOOL_NAME_PREFIXES に world と move が含まれる"""
        assert TOOL_NAME_PREFIX_WORLD in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_MOVE in TOOL_NAME_PREFIXES

    def test_prefix_descriptions_length_matches_prefixes(self):
        """プレフィックス説明の数がプレフィックス数と一致する"""
        assert len(TOOL_NAME_PREFIX_DESCRIPTIONS) == len(TOOL_NAME_PREFIXES)

    def test_prefix_format_ends_with_underscore(self):
        """プレフィックスはアンダースコアで終わる"""
        for prefix in TOOL_NAME_PREFIXES:
            assert prefix.endswith("_"), f"prefix should end with '_': {prefix}"


class TestToolNames:
    """ツール名がプレフィックス付きであること"""

    def test_no_op_has_world_prefix(self):
        """no_op は world_ プレフィックスを持つ"""
        assert TOOL_NAME_NO_OP.startswith(TOOL_NAME_PREFIX_WORLD)
        assert TOOL_NAME_NO_OP == "world_no_op"

    def test_move_to_destination_has_move_prefix(self):
        """move_to_destination は move_ プレフィックスを持つ"""
        assert TOOL_NAME_MOVE_TO_DESTINATION.startswith(TOOL_NAME_PREFIX_MOVE)
        assert TOOL_NAME_MOVE_TO_DESTINATION == "move_to_destination"
