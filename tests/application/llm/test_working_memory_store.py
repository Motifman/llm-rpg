"""InMemoryWorkingMemoryStore のテスト（正常・境界・例外）"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestInMemoryWorkingMemoryStore:
    """InMemoryWorkingMemoryStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return InMemoryWorkingMemoryStore(max_entries_per_player=10)

    def test_append_and_get_recent_returns_appended(self, store):
        """append したテキストが get_recent で取得できる"""
        player_id = PlayerId(1)
        store.append(player_id, "スライムは火が弱いかも")
        got = store.get_recent(player_id, 5)
        assert len(got) == 1
        assert got[0] == "スライムは火が弱いかも"

    def test_get_recent_empty_for_unknown_player(self, store):
        """未登録プレイヤーでは get_recent が空リストを返す"""
        got = store.get_recent(PlayerId(999), 5)
        assert got == []

    def test_get_recent_respects_limit(self, store):
        """get_recent の limit を超えない"""
        player_id = PlayerId(1)
        for i in range(5):
            store.append(player_id, f"note_{i}")
        got = store.get_recent(player_id, 2)
        assert len(got) == 2
        assert got[0] == "note_4"
        assert got[1] == "note_3"

    def test_get_recent_returns_newest_first(self, store):
        """get_recent は新しい順で返す"""
        player_id = PlayerId(1)
        store.append(player_id, "古い")
        store.append(player_id, "新しい")
        got = store.get_recent(player_id, 5)
        assert got[0] == "新しい"
        assert got[1] == "古い"

    def test_sliding_trim_to_max_entries(self):
        """max_entries を超えると古いものが捨てられる"""
        store = InMemoryWorkingMemoryStore(max_entries_per_player=3)
        player_id = PlayerId(1)
        for i in range(5):
            store.append(player_id, f"note_{i}")
        got = store.get_recent(player_id, 10)
        assert len(got) == 3
        assert got[0] == "note_4"
        assert got[1] == "note_3"
        assert got[2] == "note_2"

    def test_clear_removes_all_entries(self, store):
        """clear で全件削除"""
        player_id = PlayerId(1)
        store.append(player_id, "メモ1")
        store.append(player_id, "メモ2")
        store.clear(player_id)
        got = store.get_recent(player_id, 5)
        assert got == []

    def test_clear_empty_store_no_error(self, store):
        """空のストアを clear してもエラーにならない"""
        store.clear(PlayerId(1))

    def test_init_max_entries_zero_raises_value_error(self):
        """max_entries_per_player が 0 以下で ValueError"""
        with pytest.raises(
            ValueError, match="max_entries_per_player must be greater than 0"
        ):
            InMemoryWorkingMemoryStore(max_entries_per_player=0)

    def test_append_player_id_none_raises_type_error(self, store):
        """append に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.append(None, "text")  # type: ignore[arg-type]

    def test_append_text_not_str_raises_type_error(self, store):
        """append に text が str でないとき TypeError"""
        with pytest.raises(TypeError, match="text must be str"):
            store.append(PlayerId(1), 123)  # type: ignore[arg-type]

    def test_get_recent_player_id_none_raises_type_error(self, store):
        """get_recent に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.get_recent(None, 5)  # type: ignore[arg-type]

    def test_get_recent_negative_limit_raises_value_error(self, store):
        """get_recent の limit が負で ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            store.get_recent(PlayerId(1), -1)

    def test_clear_player_id_none_raises_type_error(self, store):
        """clear に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.clear(None)  # type: ignore[arg-type]

    def test_get_recent_limit_zero_returns_empty(self, store):
        """get_recent の limit が 0 のとき空リスト"""
        store.append(PlayerId(1), "メモ")
        got = store.get_recent(PlayerId(1), 0)
        assert got == []
