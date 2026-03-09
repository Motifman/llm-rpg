"""InMemoryTodoStore のテスト（正常・境界・例外）"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestInMemoryTodoStore:
    """InMemoryTodoStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return InMemoryTodoStore()

    def test_add_and_list_returns_added(self, store):
        """add した TODO が list_uncompleted で取得できる"""
        player_id = PlayerId(1)
        todo_id = store.add(player_id, "洞窟を探索する")
        got = store.list_uncompleted(player_id)
        assert len(got) == 1
        assert got[0].id == todo_id
        assert got[0].content == "洞窟を探索する"
        assert got[0].completed is False

    def test_complete_marks_done(self, store):
        """complete で TODO が完了になる"""
        player_id = PlayerId(1)
        todo_id = store.add(player_id, "クエストを完了する")
        result = store.complete(player_id, todo_id)
        assert result is True
        got = store.list_uncompleted(player_id)
        assert len(got) == 0

    def test_list_excludes_completed(self, store):
        """list_uncompleted は完了済みを除外する"""
        player_id = PlayerId(1)
        store.add(player_id, "やること1")
        todo_id2 = store.add(player_id, "やること2")
        store.add(player_id, "やること3")
        store.complete(player_id, todo_id2)
        got = store.list_uncompleted(player_id)
        assert len(got) == 2
        contents = [e.content for e in got]
        assert "やること1" in contents
        assert "やること3" in contents
        assert "やること2" not in contents

    def test_remove_deletes_entry(self, store):
        """remove で TODO が削除される"""
        player_id = PlayerId(1)
        todo_id = store.add(player_id, "削除するタスク")
        result = store.remove(player_id, todo_id)
        assert result is True
        got = store.list_uncompleted(player_id)
        assert len(got) == 0

    def test_list_empty_for_unknown_player(self, store):
        """未登録プレイヤーでは list_uncompleted が空リストを返す"""
        got = store.list_uncompleted(PlayerId(999))
        assert got == []

    def test_complete_invalid_id_returns_false(self, store):
        """存在しない todo_id で complete すると False"""
        result = store.complete(PlayerId(1), "non-existent-id")
        assert result is False

    def test_remove_invalid_id_returns_false(self, store):
        """存在しない todo_id で remove すると False"""
        result = store.remove(PlayerId(1), "non-existent-id")
        assert result is False

    def test_add_player_id_none_raises_type_error(self, store):
        """add に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.add(None, "content")  # type: ignore[arg-type]

    def test_add_content_not_str_raises_type_error(self, store):
        """add に content が str でないとき TypeError"""
        with pytest.raises(TypeError, match="content must be str"):
            store.add(PlayerId(1), 123)  # type: ignore[arg-type]

    def test_list_player_id_none_raises_type_error(self, store):
        """list_uncompleted に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.list_uncompleted(None)  # type: ignore[arg-type]

    def test_complete_player_id_none_raises_type_error(self, store):
        """complete に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.complete(None, "some-id")  # type: ignore[arg-type]

    def test_complete_todo_id_none_raises_type_error(self, store):
        """complete に todo_id が str でないとき TypeError"""
        with pytest.raises(TypeError, match="todo_id must be str"):
            store.complete(PlayerId(1), None)  # type: ignore[arg-type]

    def test_remove_player_id_none_raises_type_error(self, store):
        """remove に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.remove(None, "some-id")  # type: ignore[arg-type]

    def test_remove_todo_id_none_raises_type_error(self, store):
        """remove に todo_id が str でないとき TypeError"""
        with pytest.raises(TypeError, match="todo_id must be str"):
            store.remove(PlayerId(1), 123)  # type: ignore[arg-type]

    def test_complete_already_completed_returns_true(self, store):
        """既に完了済みの TODO を complete しても True（冪等）"""
        player_id = PlayerId(1)
        todo_id = store.add(player_id, "タスク")
        store.complete(player_id, todo_id)
        result = store.complete(player_id, todo_id)
        assert result is True

    def test_list_returns_newest_first(self, store):
        """list_uncompleted は追加日の新しい順で返す"""
        player_id = PlayerId(1)
        store.add(player_id, "1番目")
        store.add(player_id, "2番目")
        store.add(player_id, "3番目")
        got = store.list_uncompleted(player_id)
        assert len(got) == 3
        assert got[0].content == "3番目"
        assert got[1].content == "2番目"
        assert got[2].content == "1番目"
