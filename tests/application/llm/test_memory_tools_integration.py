"""memory_query / todo_* / working_memory_append の ToolCommandMapper 統合テスト"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_memory_query_executor():
    """MemoryQueryExecutor のモック（episodic.take / working_memory.take を返す）"""
    from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
        InMemoryEpisodeMemoryStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
        InMemoryLongTermMemoryStore,
    )
    from ai_rpg_world.application.llm.services.action_result_store import (
        DefaultActionResultStore,
    )
    from ai_rpg_world.application.llm.services.sliding_window_memory import (
        DefaultSlidingWindowMemory,
    )
    from ai_rpg_world.application.llm.services.recent_events_formatter import (
        DefaultRecentEventsFormatter,
    )

    executor = MemoryQueryExecutor(
        episode_store=InMemoryEpisodeMemoryStore(),
        long_term_store=InMemoryLongTermMemoryStore(),
        sliding_window=DefaultSlidingWindowMemory(),
        action_result_store=DefaultActionResultStore(),
        working_memory_store=InMemoryWorkingMemoryStore(),
        state_provider=lambda pid: "（テスト状態）",
        recent_events_formatter=DefaultRecentEventsFormatter(),
    )
    return executor


@pytest.fixture
def movement_service():
    return MagicMock()


@pytest.fixture
def memory_query_executor():
    return _make_memory_query_executor()


@pytest.fixture
def subagent_runner(memory_query_executor):
    return SubagentRunner(
        memory_query_executor=memory_query_executor,
        invoke_text=lambda sys, user: "副 LLM の要約結果",
    )


@pytest.fixture
def todo_store():
    return InMemoryTodoStore()


@pytest.fixture
def working_memory_store():
    return InMemoryWorkingMemoryStore()


@pytest.fixture
def mapper(
    movement_service,
    memory_query_executor,
    subagent_runner,
    todo_store,
    working_memory_store,
):
    return ToolCommandMapper(
        movement_service=movement_service,
        memory_query_executor=memory_query_executor,
        subagent_runner=subagent_runner,
        todo_store=todo_store,
        working_memory_store=working_memory_store,
    )


class TestMemoryQueryTool:
    """memory_query ツールの実行"""

    def test_execute_memory_query_success(self, mapper):
        """episodic.take(5) で成功・結果を message に"""
        result = mapper.execute(
            1,
            TOOL_NAME_MEMORY_QUERY,
            {"expr": "episodic.take(5)", "output_mode": "text"},
        )
        assert isinstance(result, LlmCommandResultDto)
        assert result.success is True
        assert result.message is not None

    def test_execute_memory_query_empty_expr_returns_failure(self, mapper):
        """expr が空のとき失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_MEMORY_QUERY,
            {"expr": " ", "output_mode": "text"},
        )
        assert result.success is False
        assert result.error_code == "MEMORY_QUERY_DSL_PARSE_ERROR"

    def test_execute_memory_query_without_executor_returns_unknown_tool(self, movement_service):
        """memory_query_executor なしのとき unknown tool"""
        mapper = ToolCommandMapper(movement_service=movement_service)
        result = mapper.execute(
            1,
            TOOL_NAME_MEMORY_QUERY,
            {"expr": "episodic.take(5)"},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestSubagentTool:
    """subagent ツールの実行"""

    def test_execute_subagent_success(self, mapper):
        """bindings と query で成功"""
        result = mapper.execute(
            1,
            TOOL_NAME_SUBAGENT,
            {
                "bindings": {"ep": "episodic.take(3)"},
                "query": "何が記録されていますか？",
            },
        )
        assert result.success is True
        assert "副 LLM の要約結果" in result.message

    def test_execute_subagent_empty_query_returns_failure(self, mapper):
        """query が空のとき失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_SUBAGENT,
            {"bindings": {"a": "episodic.take(1)"}, "query": ""},
        )
        assert result.success is False
        assert result.error_code == "SUBAGENT_ERROR"


class TestTodoTools:
    """todo_add / todo_list / todo_complete ツールの実行"""

    def test_execute_todo_add_success(self, mapper):
        """content で TODO 追加成功"""
        result = mapper.execute(
            1,
            TOOL_NAME_TODO_ADD,
            {"content": "アイテムを売却する"},
        )
        assert result.success is True
        assert "TODO を追加" in result.message
        assert "ID:" in result.message

    def test_execute_todo_add_empty_content_returns_failure(self, mapper):
        """content が空のとき失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_TODO_ADD,
            {"content": " "},
        )
        assert result.success is False
        assert result.error_code == "TODO_ERROR"

    def test_execute_todo_list_empty_returns_message(self, mapper):
        """未完了 TODO がなければメッセージ"""
        result = mapper.execute(1, TOOL_NAME_TODO_LIST, {})
        assert result.success is True
        assert "未完了の TODO はありません" in result.message

    def test_execute_todo_list_with_entries_shows_list(self, mapper):
        """TODO 追加後 list で一覧表示"""
        mapper.execute(1, TOOL_NAME_TODO_ADD, {"content": "タスクA"})
        mapper.execute(1, TOOL_NAME_TODO_ADD, {"content": "タスクB"})
        result = mapper.execute(1, TOOL_NAME_TODO_LIST, {})
        assert result.success is True
        assert "タスクA" in result.message
        assert "タスクB" in result.message

    def test_execute_todo_complete_success(self, mapper, todo_store):
        """todo_id で完了"""
        add_result = mapper.execute(1, TOOL_NAME_TODO_ADD, {"content": "完了対象"})
        assert add_result.success is True
        entries = todo_store.list_uncompleted(PlayerId(1))
        assert len(entries) == 1
        todo_id = entries[0].id
        complete_result = mapper.execute(
            1, TOOL_NAME_TODO_COMPLETE, {"todo_id": todo_id}
        )
        assert complete_result.success is True
        assert "完了" in complete_result.message

    def test_execute_todo_complete_invalid_id_returns_failure(self, mapper):
        """存在しない todo_id で失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_TODO_COMPLETE,
            {"todo_id": "nonexistent-id"},
        )
        assert result.success is False
        assert "見つかりません" in result.message or "TODO" in result.message


class TestWorkingMemoryAppendTool:
    """working_memory_append ツールの実行"""

    def test_execute_working_memory_append_success(self, mapper, working_memory_store):
        """text で作業メモに追加"""
        result = mapper.execute(
            1,
            TOOL_NAME_WORKING_MEMORY_APPEND,
            {"text": "仮説: 宝は洞窟にある"},
        )
        assert result.success is True
        assert "作業メモに追加" in result.message
        recent = working_memory_store.get_recent(PlayerId(1), 5)
        assert len(recent) == 1
        assert "宝は洞窟にある" in recent[0]

    def test_execute_working_memory_append_empty_text_returns_failure(self, mapper):
        """text が空のとき失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_WORKING_MEMORY_APPEND,
            {"text": " "},
        )
        assert result.success is False
        assert result.error_code == "WORKING_MEMORY_ERROR"


class TestUnknownTool:
    """未知ツール時の扱い"""

    def test_execute_unknown_tool_returns_failure(self, mapper):
        """登録されていないツール名で UNKNOWN_TOOL"""
        result = mapper.execute(1, "memory_unknown_tool", {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
