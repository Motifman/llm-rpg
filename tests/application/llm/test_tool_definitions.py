"""tool_catalog（register_default_tools, 定義定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
)
from ai_rpg_world.application.llm.services.tool_catalog.speech import (
    SPEECH_DEFINITION,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_SPEECH,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
)


class TestToolDefinitions:
    """ツール定義定数の内容"""


    def test_speech_definition_has_expected_name_and_params(self):
        """Issue #264 後続: 統合された SPEECH_DEFINITION は channel/content を持つ。

        channel の enum は whisper/say/shout の 3 値、target_label は properties に
        あるが whisper のみで必要 (executor で validation)。
        """
        assert SPEECH_DEFINITION.name == TOOL_NAME_SPEECH
        params = SPEECH_DEFINITION.parameters
        # 必須
        assert "channel" in params.get("properties", {})
        assert "content" in params.get("properties", {})
        assert "channel" in params.get("required", [])
        assert "content" in params.get("required", [])
        # target_label は properties にあるが required ではない (whisper のみ必要)
        assert "target_label" in params.get("properties", {})
        assert "target_label" not in params.get("required", [])
        # channel の enum は whisper/say/shout
        channel_enum = params["properties"]["channel"].get("enum")
        assert set(channel_enum) == {"whisper", "say", "shout"}


class TestRegisterDefaultTools:
    """register_default_tools の正常・例外"""


    def test_register_default_tools_with_speech_enabled_adds_speech(self):
        """Issue #264 後続: 単一 speech_speak tool が登録される (SAY/WHISPER 統合後)。"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, speech_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_SPEECH in names


    def test_register_default_tools_registry_not_registry_raises_type_error(self):
        """registry が IGameToolRegistry でないとき TypeError"""
        with pytest.raises(TypeError, match="registry must be IGameToolRegistry"):
            register_default_tools(None)  # type: ignore[arg-type]

    def test_register_default_tools_trade_only_registers_trade_family(self):
        """trade_enabled のみで取引カタログ（入退場・4 ミューテーション）が登録される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, trade_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_TRADE_ENTER in names
        assert TOOL_NAME_TRADE_EXIT in names
        assert TOOL_NAME_TRADE_OFFER in names

    def test_register_default_tools_trade_virtual_pages_adds_nav_tools(self):
        """trade_enabled かつ trade_virtual_pages_enabled で仮想取引所ナビツールが追加される"""
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_TRADE_OPEN_PAGE,
            TOOL_NAME_TRADE_VIEW_CURRENT_PAGE,
        )

        registry = DefaultGameToolRegistry()
        register_default_tools(
            registry, trade_enabled=True, trade_virtual_pages_enabled=True
        )
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_TRADE_VIEW_CURRENT_PAGE in names
        assert TOOL_NAME_TRADE_OPEN_PAGE in names

    def test_register_default_tools_sns_and_trade_both_enabled_registers_independent_catalogs(
        self,
    ):
        """両方有効時は SNS カタログと取引カタログが別々に登録される（取引は sns 必須ではない）"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, trade_enabled=True, sns_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_TRADE_OFFER in names


    def test_trade_mutation_definitions_expose_trade_ref_only(self):
        """取引ミューテーションは trade_ref のみ（trade_label はスキーマに含めない）"""
        from ai_rpg_world.application.llm.services.tool_catalog.trade import (
            TRADE_ACCEPT_DEFINITION,
            TRADE_CANCEL_DEFINITION,
            TRADE_DECLINE_DEFINITION,
        )
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_TRADE_ACCEPT,
            TOOL_NAME_TRADE_CANCEL,
            TOOL_NAME_TRADE_DECLINE,
        )

        assert TRADE_ACCEPT_DEFINITION.name == TOOL_NAME_TRADE_ACCEPT
        assert TRADE_CANCEL_DEFINITION.name == TOOL_NAME_TRADE_CANCEL
        assert TRADE_DECLINE_DEFINITION.name == TOOL_NAME_TRADE_DECLINE
        for d in (TRADE_ACCEPT_DEFINITION, TRADE_CANCEL_DEFINITION, TRADE_DECLINE_DEFINITION):
            props = d.parameters.get("properties") or {}
            assert "trade_ref" in props
            assert "trade_label" not in props
            assert d.parameters.get("required") == ["trade_ref"]

    def test_register_default_tools_sns_enabled_registers_sns_enter(self):
        """sns_enabled で sns_enter が登録される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT in names

    def test_register_default_tools_sns_definitions_use_ref_arguments(self):
        """仮想画面 SNS の書き込み系ツールは raw ID ではなく ref を表に出す"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_enabled=True)
        defs = {
            entry[0].name: entry[0] for entry in registry.get_definitions_with_resolvers()
        }

        create_reply = defs[TOOL_NAME_SNS_CREATE_REPLY].parameters
        assert "parent_post_ref" in create_reply["properties"]
        assert "parent_reply_ref" in create_reply["properties"]
        assert "parent_post_id" not in create_reply["properties"]
        assert "parent_reply_id" not in create_reply["properties"]

        like_post = defs[TOOL_NAME_SNS_LIKE_POST].parameters
        assert "post_ref" in like_post["properties"]
        assert "post_id" not in like_post["properties"]

        follow = defs[TOOL_NAME_SNS_FOLLOW].parameters
        assert "target_user_ref" in follow["properties"]
        assert "target_user_id" not in follow["properties"]

        mark_notification = defs[TOOL_NAME_SNS_MARK_NOTIFICATION_READ].parameters
        assert "notification_ref" in mark_notification["properties"]
        assert "notification_id" not in mark_notification["properties"]

    def test_register_default_tools_sns_virtual_pages_adds_navigation_tools(self):
        """sns_enabled かつ sns_virtual_pages_enabled で仮想画面ナビツールが追加される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(
            registry, sns_enabled=True, sns_virtual_pages_enabled=True
        )
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE in names

    def test_register_default_tools_virtual_pages_without_sns_does_not_add(self):
        """sns_enabled が False なら sns_virtual_pages_enabled だけではナビを足さない"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_virtual_pages_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names
