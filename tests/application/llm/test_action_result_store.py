"""DefaultActionResultStore のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestDefaultActionResultStore:
    """DefaultActionResultStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return DefaultActionResultStore(max_entries_per_player=10)

    def test_append_and_get_recent_returns_appended(self, store):
        """append した行動結果が get_recent で取得できる"""
        player_id = PlayerId(1)
        store.append(
            player_id,
            action_summary="move_to を実行",
            result_summary="スポットAに到着しました。",
        )
        got = store.get_recent(player_id, 5)
        assert len(got) == 1
        assert got[0].action_summary == "move_to を実行"
        assert got[0].result_summary == "スポットAに到着しました。"

    def test_get_recent_empty_for_unknown_player(self, store):
        """未登録プレイヤーでは get_recent が空リストを返す"""
        got = store.get_recent(PlayerId(999), 5)
        assert got == []

    def test_get_recent_respects_limit(self, store):
        """get_recent の limit を超えない"""
        player_id = PlayerId(1)
        for i in range(5):
            store.append(
                player_id,
                action_summary=f"action_{i}",
                result_summary=f"result_{i}",
            )
        got = store.get_recent(player_id, 2)
        assert len(got) == 2

    def test_append_with_occurred_at_uses_given_time(self, store):
        """occurred_at を渡すとその時刻で保存される"""
        player_id = PlayerId(1)
        at = datetime(2025, 3, 1, 12, 0, 0)
        store.append(
            player_id,
            action_summary="a",
            result_summary="b",
            occurred_at=at,
        )
        got = store.get_recent(player_id, 1)
        assert got[0].occurred_at == at

    def test_sliding_trim_to_max_entries(self):
        """max_entries_per_player を超えると古いものが捨てられる"""
        store = DefaultActionResultStore(max_entries_per_player=3)
        player_id = PlayerId(1)
        for i in range(5):
            store.append(player_id, f"a_{i}", f"r_{i}")
        got = store.get_recent(player_id, 10)
        assert len(got) == 3

    def test_init_max_entries_zero_raises_value_error(self):
        """max_entries_per_player が 0 以下で ValueError"""
        with pytest.raises(ValueError, match="max_entries_per_player must be greater than 0"):
            DefaultActionResultStore(max_entries_per_player=0)

    def test_append_player_id_none_raises_type_error(self, store):
        """append に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.append(None, "a", "b")  # type: ignore[arg-type]

    def test_append_action_summary_not_str_raises_type_error(self, store):
        """action_summary が str でないとき TypeError"""
        with pytest.raises(TypeError, match="action_summary must be str"):
            store.append(PlayerId(1), 123, "b")  # type: ignore[arg-type]

    def test_append_result_summary_not_str_raises_type_error(self, store):
        """result_summary が str でないとき TypeError"""
        with pytest.raises(TypeError, match="result_summary must be str"):
            store.append(PlayerId(1), "a", None)  # type: ignore[arg-type]

    def test_append_occurred_at_not_datetime_raises_type_error(self, store):
        """occurred_at が datetime でないとき TypeError"""
        with pytest.raises(TypeError, match="occurred_at must be datetime or None"):
            store.append(
                PlayerId(1),
                "a",
                "b",
                occurred_at="2025-01-01",  # type: ignore[arg-type]
            )

    def test_get_recent_negative_limit_raises_value_error(self, store):
        """get_recent の limit が負で ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            store.get_recent(PlayerId(1), -1)

    def test_get_recent_player_id_none_raises_type_error(self, store):
        """get_recent に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.get_recent(None, 5)  # type: ignore[arg-type]
