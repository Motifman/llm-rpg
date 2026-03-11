"""tool_constants（プレフィックス・ツール名定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_PREFIXES,
    TOOL_NAME_PREFIX_DESCRIPTIONS,
    TOOL_NAME_PREFIX_COMBAT,
    TOOL_NAME_PREFIX_CONVERSATION,
    TOOL_NAME_PREFIX_HARVEST,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SPEECH,
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)


class TestToolNamePrefixes:
    """プレフィックス定数の一貫性"""

    def test_prefixes_list_contains_expected(self):
        """TOOL_NAME_PREFIXES に主要カテゴリが含まれる"""
        assert TOOL_NAME_PREFIX_WORLD in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_MOVE in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_SPEECH in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_HARVEST in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_CONVERSATION in TOOL_NAME_PREFIXES
        assert TOOL_NAME_PREFIX_COMBAT in TOOL_NAME_PREFIXES

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

    def test_whisper_has_speech_prefix(self):
        """whisper は speech_ プレフィックスを持つ"""
        assert TOOL_NAME_WHISPER.startswith(TOOL_NAME_PREFIX_SPEECH)
        assert TOOL_NAME_WHISPER == "speech_whisper"

    def test_say_has_speech_prefix(self):
        assert TOOL_NAME_SAY.startswith(TOOL_NAME_PREFIX_SPEECH)
        assert TOOL_NAME_SAY == "speech_say"

    def test_interact_has_world_prefix(self):
        assert TOOL_NAME_INTERACT_WORLD_OBJECT.startswith(TOOL_NAME_PREFIX_WORLD)
        assert TOOL_NAME_INTERACT_WORLD_OBJECT == "world_interact"

    def test_harvest_start_has_harvest_prefix(self):
        assert TOOL_NAME_HARVEST_START.startswith(TOOL_NAME_PREFIX_HARVEST)
        assert TOOL_NAME_HARVEST_START == "harvest_start"

    def test_harvest_cancel_has_harvest_prefix(self):
        assert TOOL_NAME_HARVEST_CANCEL.startswith(TOOL_NAME_PREFIX_HARVEST)
        assert TOOL_NAME_HARVEST_CANCEL == "harvest_cancel"

    def test_change_attention_has_world_prefix(self):
        assert TOOL_NAME_CHANGE_ATTENTION.startswith(TOOL_NAME_PREFIX_WORLD)

    def test_place_and_destroy_have_world_prefix(self):
        assert TOOL_NAME_PLACE_OBJECT.startswith(TOOL_NAME_PREFIX_WORLD)
        assert TOOL_NAME_DESTROY_PLACEABLE.startswith(TOOL_NAME_PREFIX_WORLD)

    def test_conversation_advance_has_conversation_prefix(self):
        assert TOOL_NAME_CONVERSATION_ADVANCE.startswith(TOOL_NAME_PREFIX_CONVERSATION)

    def test_chest_tools_have_world_prefix(self):
        assert TOOL_NAME_CHEST_STORE.startswith(TOOL_NAME_PREFIX_WORLD)
        assert TOOL_NAME_CHEST_TAKE.startswith(TOOL_NAME_PREFIX_WORLD)

    def test_combat_use_skill_has_combat_prefix(self):
        assert TOOL_NAME_COMBAT_USE_SKILL.startswith(TOOL_NAME_PREFIX_COMBAT)
