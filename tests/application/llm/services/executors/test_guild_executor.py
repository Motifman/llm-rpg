"""GuildToolExecutor のユニットテスト"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.guild_executor import GuildToolExecutor
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
)


@pytest.fixture
def guild_service():
    return MagicMock()


@pytest.fixture
def executor_with_service(guild_service):
    return GuildToolExecutor(guild_service=guild_service)


@pytest.fixture
def executor_without_service():
    return GuildToolExecutor(guild_service=None)


class TestGuildToolExecutorGetHandlers:
    """get_handlers() の振る舞い"""

    def test_with_guild_service_returns_seven_handlers(self, executor_with_service):
        """guild_service があるとき 7 ツールのハンドラを返す"""
        handlers = executor_with_service.get_handlers()
        assert len(handlers) == 7
        assert TOOL_NAME_GUILD_CREATE in handlers
        assert TOOL_NAME_GUILD_ADD_MEMBER in handlers
        assert TOOL_NAME_GUILD_CHANGE_ROLE in handlers
        assert TOOL_NAME_GUILD_DISBAND in handlers
        assert TOOL_NAME_GUILD_LEAVE in handlers
        assert TOOL_NAME_GUILD_DEPOSIT_BANK in handlers
        assert TOOL_NAME_GUILD_WITHDRAW_BANK in handlers

    def test_without_guild_service_returns_empty(self, executor_without_service):
        """guild_service が None のとき空辞書"""
        handlers = executor_without_service.get_handlers()
        assert handlers == {}


class TestGuildToolExecutorCreate:
    """guild_create の実行"""

    def test_create_success_returns_dto(self, executor_with_service, guild_service):
        guild_service.create_guild.return_value = MagicMock(
            success=True, message="ギルドを作成しました。"
        )
        result = executor_with_service._execute_guild_create(
            1,
            {"spot_id": 1, "location_area_id": 10, "name": "冒険者ギルド", "description": "一緒に冒険"},
        )
        assert result.success is True
        assert "作成" in result.message or result.message
        guild_service.create_guild.assert_called_once()

    def test_create_missing_spot_id_returns_invalid_arg(self, executor_with_service):
        result = executor_with_service._execute_guild_create(
            1,
            {"location_area_id": 10, "name": "テスト"},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"

    def test_create_missing_name_returns_invalid_arg(self, executor_with_service):
        result = executor_with_service._execute_guild_create(
            1,
            {"spot_id": 1, "location_area_id": 10},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"

    def test_create_without_service_returns_unknown_tool(self, executor_without_service):
        result = executor_without_service._execute_guild_create(
            1, {"spot_id": 1, "location_area_id": 10, "name": "テスト"}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestGuildToolExecutorAddMember:
    """guild_add_member の実行"""

    def test_add_member_success_returns_dto(self, executor_with_service, guild_service):
        guild_service.add_member.return_value = MagicMock(
            success=True, message="招待しました。"
        )
        result = executor_with_service._execute_guild_add_member(
            1, {"guild_id": 10, "new_member_player_id": 2}
        )
        assert result.success is True
        guild_service.add_member.assert_called_once()
        cmd = guild_service.add_member.call_args[0][0]
        assert cmd.guild_id == 10
        assert cmd.inviter_player_id == 1
        assert cmd.new_member_player_id == 2

    def test_add_member_without_service_returns_unknown_tool(
        self, executor_without_service
    ):
        result = executor_without_service._execute_guild_add_member(
            1, {"guild_id": 10, "new_member_player_id": 2}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestGuildToolExecutorDisband:
    """guild_disband の実行"""

    def test_disband_success_returns_dto(self, executor_with_service, guild_service):
        guild_service.disband_guild.return_value = MagicMock(
            success=True, message="ギルドを解散しました。"
        )
        result = executor_with_service._execute_guild_disband(
            1, {"guild_id": 10}
        )
        assert result.success is True
        guild_service.disband_guild.assert_called_once()
        cmd = guild_service.disband_guild.call_args[0][0]
        assert cmd.guild_id == 10
        assert cmd.player_id == 1

    def test_disband_without_service_returns_unknown_tool(
        self, executor_without_service
    ):
        result = executor_without_service._execute_guild_disband(1, {"guild_id": 10})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestGuildToolExecutorIntegrationWithMapper:
    """ToolCommandMapper 経由での統合（get_handlers のマージ動作確認）"""

    def test_handlers_are_callable_with_correct_signature(
        self, executor_with_service, guild_service
    ):
        """get_handlers() で返るハンドラが (player_id, args) で呼び出せる"""
        guild_service.create_guild.return_value = MagicMock(
            success=True, message="作成しました。"
        )
        handlers = executor_with_service.get_handlers()
        result = handlers[TOOL_NAME_GUILD_CREATE](
            1,
            {"spot_id": 1, "location_area_id": 10, "name": "テスト", "description": ""},
        )
        assert result.success is True
