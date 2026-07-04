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
    TOOL_NAME_PREFIX_SKILL,
    TOOL_NAME_PREFIX_SPEECH,
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SPEECH,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
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
        assert TOOL_NAME_PREFIX_SKILL in TOOL_NAME_PREFIXES

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

    def test_speech_tool_name_is_speak(self):
        """PR-DD (Y_after_pr639_640 後続): 発話 tool 名は ``speak`` に短縮。
        歴史的経緯:
        - Issue #264: 旧 SAY / WHISPER 2 tool を統合、``speech_speak`` 命名
        - PR-DD: ``speech`` と ``speak`` の意味重複を解消し ``speak`` に短縮
        """
        assert TOOL_NAME_SPEECH == "speak"
        # Python 側の PREFIX 定数は歴史的名残 (テーブル入りしていない他所で
        # 参照される可能性を否定できないため据え置く)
        assert TOOL_NAME_PREFIX_SPEECH == "speech_"

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

    def test_skill_management_tools_have_skill_prefix(self):
        assert TOOL_NAME_SKILL_EQUIP.startswith(TOOL_NAME_PREFIX_SKILL)
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL.startswith(TOOL_NAME_PREFIX_SKILL)
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL.startswith(TOOL_NAME_PREFIX_SKILL)
        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE.startswith(TOOL_NAME_PREFIX_SKILL)
