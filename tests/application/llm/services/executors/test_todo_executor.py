"""TodoToolExecutor のユニットテスト

Phase 3 Step 3a-3: Resolver+WorldId 必須 + provision 済 Being を前提に書換。
共通 fixture が make_memo_being_setup() で Being を 1 体 provision し、
todo_store として共有する。
"""

import pytest

from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.application.llm._memo_being_test_helpers import (
    MemoBeingTestSetup,
    make_memo_being_setup,
)


@pytest.fixture
def being_setup() -> MemoBeingTestSetup:
    setup = make_memo_being_setup()
    # テスト内で使う player_id = 1 を provision (handler 引数 1 と一致)
    setup.provision(1)
    return setup


@pytest.fixture
def todo_store(being_setup: MemoBeingTestSetup) -> InMemoryTodoStore:
    # 共有 store を InMemoryTodoStore として参照 (= 既存 fixture と互換)
    return being_setup.memo_store


@pytest.fixture
def executor_with_store(being_setup: MemoBeingTestSetup) -> TodoToolExecutor:
    return TodoToolExecutor(
        todo_store=being_setup.memo_store,
        being_attachment_resolver=being_setup.resolver,
        default_world_id=being_setup.world_id,
    )


@pytest.fixture
def executor_without_store(being_setup: MemoBeingTestSetup) -> TodoToolExecutor:
    return TodoToolExecutor(
        todo_store=None,
        being_attachment_resolver=being_setup.resolver,
        default_world_id=being_setup.world_id,
    )


class TestTodoToolExecutorGetHandlers:
    """get_handlers() の振る舞い"""

    def test_with_todo_store_returns_three_handlers(self, executor_with_store):
        """todo_store があるとき 3 ツールのハンドラを返す"""
        handlers = executor_with_store.get_handlers()
        assert len(handlers) == 3
        assert TOOL_NAME_MEMO_ADD in handlers
        assert TOOL_NAME_MEMO_LIST in handlers
        assert TOOL_NAME_MEMO_DONE in handlers

    def test_without_todo_store_returns_empty(self, executor_without_store):
        """todo_store が None のとき空辞書"""
        handlers = executor_without_store.get_handlers()
        assert handlers == {}


class TestTodoToolExecutorAdd:
    """todo_add の実行"""

    def test_add_success_returns_dto_with_id(self, executor_with_store):
        result = executor_with_store._execute_memo_add(
            1, {"content": "タスクを追加"}
        )
        assert result.success is True
        assert "メモを追加しました" in result.message
        assert "ID:" in result.message

    def test_add_empty_content_returns_todo_error(self, executor_with_store):
        result = executor_with_store._execute_memo_add(1, {"content": "   "})
        assert result.success is False
        assert result.error_code == "TODO_ERROR"
        assert result.remediation is not None

    def test_add_without_store_returns_unknown_tool(self, executor_without_store):
        result = executor_without_store._execute_memo_add(
            1, {"content": "タスク"}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestTodoToolExecutorList:
    """todo_list の実行"""

    def test_list_empty_returns_message(self, executor_with_store):
        result = executor_with_store._execute_memo_list(1, {})
        assert result.success is True
        assert "未完了のメモはありません" in result.message

    def test_list_with_entries_shows_content(self, executor_with_store):
        executor_with_store._execute_memo_add(1, {"content": "タスクA"})
        executor_with_store._execute_memo_add(1, {"content": "タスクB"})
        result = executor_with_store._execute_memo_list(1, {})
        assert result.success is True
        assert "タスクA" in result.message
        assert "タスクB" in result.message

    def test_list_without_store_returns_unknown_tool(self, executor_without_store):
        result = executor_without_store._execute_memo_list(1, {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestTodoToolExecutorComplete:
    """memo_done の実行 (常に memo_ids 配列を受ける、batch 対応)"""

    def test_complete_success_returns_dto(self, executor_with_store, todo_store, being_setup):
        """単一 ID を 1 要素配列で渡すと完了する。"""
        executor_with_store._execute_memo_add(1, {"content": "完了対象"})
        entries = todo_store.list_uncompleted_by_being(being_setup.being_id_for(1))
        todo_id = entries[0].id
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": [todo_id]}
        )
        assert result.success is True
        assert "完了" in result.message

    def test_complete_invalid_id_returns_failure(self, executor_with_store):
        """存在しない単一 ID は全件 not_found となり失敗を返す。"""
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": ["nonexistent-id"]}
        )
        assert result.success is False
        assert "見つかりません" in result.message

    def test_complete_empty_array_returns_todo_error(self, executor_with_store):
        """空配列は TODO_ERROR を返す。"""
        result = executor_with_store._execute_memo_done(1, {"memo_ids": []})
        assert result.success is False
        assert result.error_code == "TODO_ERROR"

    def test_complete_missing_memo_ids_returns_todo_error(self, executor_with_store):
        """memo_ids キー欠如時も TODO_ERROR。"""
        result = executor_with_store._execute_memo_done(1, {})
        assert result.success is False
        assert result.error_code == "TODO_ERROR"

    def test_complete_memo_ids_with_non_string_returns_todo_error(
        self, executor_with_store
    ):
        """配列要素が string でなければ TODO_ERROR。"""
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": [123]}  # type: ignore[list-item]
        )
        assert result.success is False
        assert result.error_code == "TODO_ERROR"

    def test_complete_without_store_returns_unknown_tool(self, executor_without_store):
        """memo_store 未注入時は UNKNOWN_TOOL を返す。"""
        result = executor_without_store._execute_memo_done(
            1, {"memo_ids": ["todo-1"]}
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestMemoExecutorBatchComplete:
    """memo_done の batch 完了挙動 (Issue #228)。"""

    def test_複数_id_を一括で完了できる(self, executor_with_store, todo_store, being_setup):
        """配列に複数 ID を渡すと全て完了状態になる。"""
        executor_with_store._execute_memo_add(1, {"content": "A"})
        executor_with_store._execute_memo_add(1, {"content": "B"})
        executor_with_store._execute_memo_add(1, {"content": "C"})
        ids = [e.id for e in todo_store.list_uncompleted_by_being(being_setup.being_id_for(1))]
        result = executor_with_store._execute_memo_done(1, {"memo_ids": ids})
        assert result.success is True
        # 3 件全て完了したので remaining は 0
        assert todo_store.list_uncompleted_by_being(being_setup.being_id_for(1)) == []
        # message に 3 件まとめて完了した旨が含まれる
        assert "3" in result.message

    def test_存在する_id_と存在しない_id_が混在しても_存在分は完了する(
        self, executor_with_store, todo_store, being_setup
    ):
        """部分成功: 存在する ID は done、存在しない ID は not_found として個別報告。"""
        executor_with_store._execute_memo_add(1, {"content": "A"})
        valid_id = todo_store.list_uncompleted_by_being(being_setup.being_id_for(1))[0].id
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": [valid_id, "nonexistent-xxx"]}
        )
        # 1 件は完了したので overall success
        assert result.success is True
        assert "見つかりません" in result.message
        assert "nonexistent-xxx" in result.message
        # Issue #276: 完了 ID は短縮形 (先頭 6 文字 + …) で表示される
        assert valid_id[:6] in result.message
        # 有効 ID 側は実際に completed 化されている
        assert todo_store.list_uncompleted_by_being(being_setup.being_id_for(1)) == []

    def test_重複_id_を含めても二重完了でエラーにならない(
        self, executor_with_store, todo_store, being_setup
    ):
        """同じ ID を 2 回含めると、1 回目で done、2 回目は not_found 扱い。"""
        executor_with_store._execute_memo_add(1, {"content": "A"})
        memo_id = todo_store.list_uncompleted_by_being(being_setup.being_id_for(1))[0].id
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": [memo_id, memo_id]}
        )
        # 1 件は完了し、2 回目は not_found なので overall success
        assert result.success is True
        # Issue #276: 完了 ID は短縮形で表示される
        assert memo_id[:6] in result.message

    def test_短縮形_prefix_で完了できる(self, executor_with_store, todo_store, being_setup):
        """Issue #276: memo_done は full UUID と先頭 6 文字短縮形のどちらも
        受け付ける (git commit hash 風 prefix 一致)。"""
        executor_with_store._execute_memo_add(1, {"content": "A"})
        full_id = todo_store.list_uncompleted_by_being(being_setup.being_id_for(1))[0].id
        short = full_id[:6]
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": [short]}
        )
        assert result.success is True
        # 完了済み
        assert todo_store.list_uncompleted_by_being(being_setup.being_id_for(1)) == []

    def test_曖昧な_prefix_は_ambiguous_エラー(self, executor_with_store, todo_store, being_setup):
        """同じ先頭文字で始まる 2 つの memo に短縮形が一致すると、ambiguous
        として個別報告される。"""
        # uuid4 はランダムなので、無理やり同じ先頭にするためにモンキーパッチで対応
        # ここでは being store に直接 ID を仕込む簡易テスト
        from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
        from datetime import datetime
        being_id = being_setup.being_id_for(1)
        todo_store._being_store[being_id] = [
            MemoEntry(
                id="abc123-aaa",
                content="A",
                added_at=datetime.now(),
                completed=False,
            ),
            MemoEntry(
                id="abc123-bbb",
                content="B",
                added_at=datetime.now(),
                completed=False,
            ),
        ]
        todo_store._being_id_to_index[being_id] = {"abc123-aaa": 0, "abc123-bbb": 1}
        result = executor_with_store._execute_memo_done(
            1, {"memo_ids": ["abc123"]}
        )
        # どちらも未完了のまま
        assert len(todo_store.list_uncompleted_by_being(being_id)) == 2
        assert result.success is False
        assert "曖昧" in result.message


class TestTodoToolExecutorIntegrationWithMapper:
    """ToolCommandMapper 経由での統合（get_handlers のマージ動作確認）"""

    def test_handlers_are_callable_with_correct_signature(
        self, executor_with_store, todo_store
    ):
        """get_handlers() で返るハンドラが (player_id, args) で呼び出せる"""
        handlers = executor_with_store.get_handlers()
        add_result = handlers[TOOL_NAME_MEMO_ADD](1, {"content": "テスト"})
        assert add_result.success is True
        list_result = handlers[TOOL_NAME_MEMO_LIST](1, {})
        assert list_result.success is True
