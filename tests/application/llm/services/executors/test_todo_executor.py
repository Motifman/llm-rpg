"""TodoToolExecutor のユニットテスト"""

import pytest

from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@pytest.fixture
def todo_store():
    return InMemoryTodoStore()


@pytest.fixture
def executor_with_store(todo_store):
    return TodoToolExecutor(todo_store=todo_store)


@pytest.fixture
def executor_without_store():
    return TodoToolExecutor(todo_store=None)


class TestTodoToolExecutorGetHandlers:
    """get_handlers() の振る舞い"""

    def test_with_todo_store_returns_three_handlers(self, executor_with_store):
        """todo_store があるとき 3 ツールのハンドラを返す"""
        handlers = executor_with_store.get_handlers()
        assert len(handlers) == 3
        assert TOOL_NAME_TODO_ADD in handlers
        assert TOOL_NAME_TODO_LIST in handlers
        assert TOOL_NAME_TODO_COMPLETE in handlers

    def test_without_todo_store_returns_empty(self, executor_without_store):
        """todo_store が None のとき空辞書"""
        handlers = executor_without_store.get_handlers()
        assert handlers == {}


class TestTodoToolExecutorAdd:
    """todo_add の実行"""

    def test_add_success_returns_dto_with_id(self, executor_with_store):
        result = executor_with_store._execute_todo_add(
            1, {"content": "タスクを追加"}
        )
        assert result.success is True
        assert "TODO を追加" in result.message
        assert "ID:" in result.message

    def test_add_empty_content_returns_todo_error(self, executor_with_store):
        result = executor_with_store._execute_todo_add(1, {"content": "   "})
        assert result.success is False
        assert result.error_code == "TODO_ERROR"
        assert result.remediation is not None

    def test_add_without_store_returns_unknown_tool(self, executor_without_store):
        result = executor_without_store._execute_todo_add(
            1, {"content": "タスク"}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestTodoToolExecutorList:
    """todo_list の実行"""

    def test_list_empty_returns_message(self, executor_with_store):
        result = executor_with_store._execute_todo_list(1, {})
        assert result.success is True
        assert "未完了の TODO はありません" in result.message

    def test_list_with_entries_shows_content(self, executor_with_store):
        executor_with_store._execute_todo_add(1, {"content": "タスクA"})
        executor_with_store._execute_todo_add(1, {"content": "タスクB"})
        result = executor_with_store._execute_todo_list(1, {})
        assert result.success is True
        assert "タスクA" in result.message
        assert "タスクB" in result.message

    def test_list_without_store_returns_unknown_tool(self, executor_without_store):
        result = executor_without_store._execute_todo_list(1, {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestTodoToolExecutorComplete:
    """todo_complete の実行"""

    def test_complete_success_returns_dto(self, executor_with_store, todo_store):
        executor_with_store._execute_todo_add(1, {"content": "完了対象"})
        entries = todo_store.list_uncompleted(PlayerId(1))
        todo_id = entries[0].id
        result = executor_with_store._execute_todo_complete(
            1, {"todo_id": todo_id}
        )
        assert result.success is True
        assert "完了" in result.message

    def test_complete_invalid_id_returns_failure(self, executor_with_store):
        result = executor_with_store._execute_todo_complete(
            1, {"todo_id": "nonexistent-id"}
        )
        assert result.success is False
        assert "見つかりません" in result.message

    def test_complete_empty_todo_id_returns_todo_error(self, executor_with_store):
        result = executor_with_store._execute_todo_complete(1, {"todo_id": "  "})
        assert result.success is False
        assert result.error_code == "TODO_ERROR"

    def test_complete_without_store_returns_unknown_tool(self, executor_without_store):
        result = executor_without_store._execute_todo_complete(
            1, {"todo_id": "todo-1"}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestTodoToolExecutorIntegrationWithMapper:
    """ToolCommandMapper 経由での統合（get_handlers のマージ動作確認）"""

    def test_handlers_are_callable_with_correct_signature(
        self, executor_with_store, todo_store
    ):
        """get_handlers() で返るハンドラが (player_id, args) で呼び出せる"""
        handlers = executor_with_store.get_handlers()
        add_result = handlers[TOOL_NAME_TODO_ADD](1, {"content": "テスト"})
        assert add_result.success is True
        list_result = handlers[TOOL_NAME_TODO_LIST](1, {})
        assert list_result.success is True
