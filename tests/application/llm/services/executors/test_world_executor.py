"""WorldToolExecutor のユニットテスト"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.world_executor import WorldToolExecutor
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_PLACE_OBJECT,
)


@pytest.fixture
def interaction_service():
    return MagicMock()


@pytest.fixture
def harvest_service():
    svc = MagicMock()
    svc.start_harvest_by_target.return_value = MagicMock(success=True, message="採集を開始")
    svc.cancel_harvest_by_target.return_value = MagicMock(success=True, message="採集を中断")
    return svc


@pytest.fixture
def attention_service():
    return MagicMock()


@pytest.fixture
def executor_with_world_services(
    interaction_service,
    harvest_service,
    attention_service,
):
    return WorldToolExecutor(
        interaction_service=interaction_service,
        harvest_service=harvest_service,
        attention_service=attention_service,
    )


@pytest.fixture
def executor_without_services():
    return WorldToolExecutor()


class TestWorldToolExecutorGetHandlers:
    """get_handlers() の振る舞い"""

    def test_with_services_returns_twelve_handlers(self, executor_with_world_services):
        """必要なサービスがあるとき 12 ツールのハンドラを返す"""
        handlers = executor_with_world_services.get_handlers()
        assert len(handlers) == 13
        assert TOOL_NAME_INSPECT_ITEM in handlers
        assert TOOL_NAME_INSPECT_TARGET in handlers
        assert TOOL_NAME_INTERACT_WORLD_OBJECT in handlers
        assert TOOL_NAME_HARVEST_START in handlers
        assert TOOL_NAME_HARVEST_CANCEL in handlers
        assert TOOL_NAME_CHANGE_ATTENTION in handlers
        assert TOOL_NAME_CONVERSATION_ADVANCE in handlers
        assert TOOL_NAME_PLACE_OBJECT in handlers
        assert TOOL_NAME_DESTROY_PLACEABLE in handlers
        assert TOOL_NAME_DROP_ITEM in handlers
        assert TOOL_NAME_CHEST_STORE in handlers
        assert TOOL_NAME_CHEST_TAKE in handlers
        assert TOOL_NAME_COMBAT_USE_SKILL in handlers


class TestWorldToolExecutorValidation:
    """World サービスのインターフェース検証"""

    def test_interaction_service_without_interact_world_object_raises_type_error(self):
        """interaction_service に interact_world_object が無いとき TypeError"""
        with pytest.raises(TypeError, match="interaction_service must have a callable interact_world_object"):
            WorldToolExecutor(interaction_service=object())

    def test_harvest_service_without_start_raises_type_error(self):
        """harvest_service に start_harvest_by_target が無いとき TypeError"""
        svc = MagicMock()
        del svc.start_harvest_by_target
        with pytest.raises(TypeError, match="start_harvest_by_target"):
            WorldToolExecutor(harvest_service=svc)

    def test_harvest_service_without_cancel_raises_type_error(self):
        """harvest_service に cancel_harvest_by_target が無いとき TypeError"""
        svc = MagicMock()
        del svc.cancel_harvest_by_target
        with pytest.raises(TypeError, match="cancel_harvest_by_target"):
            WorldToolExecutor(harvest_service=svc)

    def test_all_none_accepts(self):
        """全サービスが None のときは検証を通過"""
        executor = WorldToolExecutor()
        handlers = executor.get_handlers()
        assert len(handlers) == 13  # 各ハンドラは実行時に None チェック


class TestWorldToolExecutorInteract:
    """interact_world_object の実行"""

    def test_interact_success_returns_dto(self, executor_with_world_services, interaction_service):
        result = executor_with_world_services._execute_interact_world_object(
            1,
            {"target_world_object_id": 200, "target_display_name": "老人"},
        )
        assert result.success is True
        assert "老人" in result.message
        interaction_service.interact_world_object.assert_called_once()

    def test_interact_without_service_returns_failure(self, executor_without_services):
        result = executor_without_services._execute_interact_world_object(
            1, {"target_world_object_id": 200}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestWorldToolExecutorHarvest:
    """harvest_start / harvest_cancel の実行"""

    def test_harvest_start_success(self, executor_with_world_services, harvest_service):
        result = executor_with_world_services._execute_harvest_start(
            1, {"target_world_object_id": 300}
        )
        assert result.success is True
        assert "採集" in result.message
        harvest_service.start_harvest_by_target.assert_called_once_with(
            player_id=1, target_world_object_id=300
        )

    def test_harvest_cancel_success(self, executor_with_world_services, harvest_service):
        result = executor_with_world_services._execute_harvest_cancel(
            1, {"target_world_object_id": 300}
        )
        assert result.success is True
        assert "中断" in result.message
        harvest_service.cancel_harvest_by_target.assert_called_once_with(
            player_id=1, target_world_object_id=300
        )

    def test_harvest_without_service_returns_failure(self, executor_without_services):
        result = executor_without_services._execute_harvest_start(
            1, {"target_world_object_id": 300}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestWorldToolExecutorIntegrationWithMapper:
    """ToolCommandMapper 経由での統合"""

    def test_handlers_are_callable(
        self, executor_with_world_services, interaction_service
    ):
        """get_handlers() で返るハンドラが (player_id, args) で呼び出せる"""
        interaction_service.interact_world_object.return_value = None
        handlers = executor_with_world_services.get_handlers()
        result = handlers[TOOL_NAME_INTERACT_WORLD_OBJECT](
            1, {"target_world_object_id": 100, "target_display_name": "箱"}
        )
        assert result.success is True
