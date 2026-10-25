"""tool_constants（プレフィックス・ツール名定数）のテスト"""

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_PREFIX_COMBAT,
    TOOL_NAME_PREFIX_CONVERSATION,
    TOOL_NAME_PREFIX_DESCRIPTIONS,
    TOOL_NAME_PREFIX_HARVEST,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SKILL,
    TOOL_NAME_PREFIX_SPEECH,
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_PREFIXES,
    TOOL_NAME_SPEECH,
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
