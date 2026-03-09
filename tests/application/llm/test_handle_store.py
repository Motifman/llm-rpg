"""HandleStore のテスト（正常系・異常系・境界・データ分離）"""

import pytest

from ai_rpg_world.application.llm.services.handle_store import (
    InMemoryHandleStore,
    generate_handle_id,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestInMemoryHandleStore:
    """InMemoryHandleStore の包括的なテストスイート"""

    # ===== 正常系のテスト =====

    class TestPutAndGet:
        """put / get の正常動作"""

        def test_put_and_get_returns_same_data(self):
            """put で保存したデータを get で取得できる"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            data = [{"id": "e1"}, {"id": "e2"}]
            hid = generate_handle_id()
            store.put(pid, hid, data, "episodic.take(10)")
            got = store.get(pid, hid)
            assert got == data

        def test_put_empty_list_accepted(self):
            """空リストの data も保存できる"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            hid = generate_handle_id()
            store.put(pid, hid, [], "episodic.take(0)")
            got = store.get(pid, hid)
            assert got == []

        def test_put_empty_expr_accepted(self):
            """空文字の expr も許容する（契約上 str であれば可）"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            hid = generate_handle_id()
            store.put(pid, hid, [{"x": 1}], "")
            got = store.get(pid, hid)
            assert got == [{"x": 1}]

        def test_put_overwrites_same_handle_id(self):
            """同一 handle_id に再 put すると上書きされる"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            hid = "h_abc123def456"
            store.put(pid, hid, [{"old": 1}], "expr1")
            store.put(pid, hid, [{"new": 2}], "expr2")
            got = store.get(pid, hid)
            assert got == [{"new": 2}]

    class TestGetNonexistent:
        """存在しない handle の取得"""

        def test_get_nonexistent_handle_returns_none(self):
            """存在しない handle_id で get すると None"""
            store = InMemoryHandleStore()
            got = store.get(PlayerId(1), "h_nonexistent")
            assert got is None

        def test_get_after_clear_player_returns_none(self):
            """clear_player 後に get すると None"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            hid = generate_handle_id()
            store.put(pid, hid, [{"x": 1}], "episodic.take(5)")
            store.clear_player(pid)
            assert store.get(pid, hid) is None

    class TestClearPlayer:
        """clear_player の動作"""

        def test_clear_player_removes_all_handles_for_player(self):
            """clear_player で当該プレイヤーの全 handle が削除される"""
            store = InMemoryHandleStore()
            pid = PlayerId(1)
            hid1 = generate_handle_id()
            hid2 = generate_handle_id()
            store.put(pid, hid1, [{"a": 1}], "expr1")
            store.put(pid, hid2, [{"b": 2}], "expr2")
            store.clear_player(pid)
            assert store.get(pid, hid1) is None
            assert store.get(pid, hid2) is None

        def test_clear_player_does_not_affect_other_players(self):
            """clear_player は他プレイヤーの handle に影響しない"""
            store = InMemoryHandleStore()
            pid1 = PlayerId(1)
            pid2 = PlayerId(2)
            hid = generate_handle_id()
            store.put(pid1, hid, [{"p1": 1}], "expr1")
            store.put(pid2, hid, [{"p2": 2}], "expr2")
            store.clear_player(pid1)
            assert store.get(pid1, hid) is None
            assert store.get(pid2, hid) == [{"p2": 2}]

    class TestDataIsolation:
        """プレイヤー間のデータ分離"""

        def test_different_players_same_handle_id_isolated(self):
            """異なるプレイヤーは同じ handle_id でも別データを保持"""
            store = InMemoryHandleStore()
            pid1 = PlayerId(1)
            pid2 = PlayerId(2)
            hid = "h_sharedhandle12"
            store.put(pid1, hid, [{"player": 1}], "expr1")
            store.put(pid2, hid, [{"player": 2}], "expr2")
            assert store.get(pid1, hid) == [{"player": 1}]
            assert store.get(pid2, hid) == [{"player": 2}]

    # ===== 異常系（バリデーション）のテスト =====

    class TestPutValidation:
        """put の入力バリデーション"""

        @pytest.fixture
        def store(self):
            return InMemoryHandleStore()

        @pytest.fixture
        def valid_pid(self):
            return PlayerId(1)

        @pytest.fixture
        def valid_hid(self):
            return generate_handle_id()

        def test_put_player_id_not_player_id_raises(self, store, valid_hid):
            """player_id が PlayerId でないとき TypeError"""
            with pytest.raises(TypeError, match="player_id must be PlayerId"):
                store.put(1, valid_hid, [], "expr")  # type: ignore[arg-type]

        def test_put_handle_id_empty_raises(self, store, valid_pid):
            """handle_id が空文字のとき TypeError"""
            with pytest.raises(TypeError, match="handle_id must be non-empty str"):
                store.put(valid_pid, "", [], "expr")

        def test_put_handle_id_not_str_raises(self, store, valid_pid):
            """handle_id が str でないとき TypeError"""
            with pytest.raises(TypeError, match="handle_id must be non-empty str"):
                store.put(valid_pid, 123, [], "expr")  # type: ignore[arg-type]

        def test_put_data_not_list_raises(self, store, valid_pid, valid_hid):
            """data が list でないとき TypeError"""
            with pytest.raises(TypeError, match="data must be list"):
                store.put(valid_pid, valid_hid, "not a list", "expr")  # type: ignore[arg-type]
            with pytest.raises(TypeError, match="data must be list"):
                store.put(valid_pid, valid_hid, {"dict": 1}, "expr")  # type: ignore[arg-type]

        def test_put_expr_not_str_raises(self, store, valid_pid, valid_hid):
            """expr が str でないとき TypeError"""
            with pytest.raises(TypeError, match="expr must be str"):
                store.put(valid_pid, valid_hid, [{"a": 1}], None)  # type: ignore[arg-type]
            with pytest.raises(TypeError, match="expr must be str"):
                store.put(valid_pid, valid_hid, [{"a": 1}], 123)  # type: ignore[arg-type]

    class TestGetValidation:
        """get の入力バリデーション"""

        def test_get_player_id_not_player_id_raises(self):
            """player_id が PlayerId でないとき TypeError"""
            store = InMemoryHandleStore()
            with pytest.raises(TypeError, match="player_id must be PlayerId"):
                store.get(1, "h_x")  # type: ignore[arg-type]

    class TestClearPlayerValidation:
        """clear_player の入力バリデーション"""

        def test_clear_player_player_id_not_player_id_raises(self):
            """player_id が PlayerId でないとき TypeError"""
            store = InMemoryHandleStore()
            with pytest.raises(TypeError, match="player_id must be PlayerId"):
                store.clear_player(1)  # type: ignore[arg-type]

    # ===== generate_handle_id のテスト =====

    class TestGenerateHandleId:
        """generate_handle_id の形式・一意性"""

        def test_format_starts_with_h_underscore(self):
            """handle_id は h_ で始まる"""
            hid = generate_handle_id()
            assert hid.startswith("h_")

        def test_format_length(self):
            """handle_id は h_ + 12 hex = 14 文字"""
            hid = generate_handle_id()
            assert len(hid) == 14

        def test_format_hex_part(self):
            """h_ 以降は16進文字のみ"""
            hid = generate_handle_id()
            hex_part = hid[2:]
            assert len(hex_part) == 12
            assert all(c in "0123456789abcdef" for c in hex_part)

        def test_generates_unique_ids(self):
            """複数回呼ぶと異なる id が返る"""
            ids = [generate_handle_id() for _ in range(10)]
            assert len(set(ids)) == 10
