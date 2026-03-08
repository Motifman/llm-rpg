"""InMemoryEpisodeMemoryStore のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime, timedelta

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_entry(
    eid: str = "ep1",
    context: str = "洞窟にいた",
    action: str = "move_to_destination",
    outcome: str = "到着した",
    entity_ids: tuple = ("loc_1",),
    location_id: str | None = "loc_1",
    ts: datetime | None = None,
    importance: str = "medium",
    surprise: bool = False,
    recall_count: int = 0,
    scope_keys: tuple = (),
) -> EpisodeMemoryEntry:
    return EpisodeMemoryEntry(
        id=eid,
        context_summary=context,
        action_taken=action,
        outcome_summary=outcome,
        entity_ids=entity_ids,
        location_id=location_id,
        timestamp=ts or datetime.now(),
        importance=importance,
        surprise=surprise,
        recall_count=recall_count,
        scope_keys=scope_keys,
    )


class TestInMemoryEpisodeMemoryStore:
    """InMemoryEpisodeMemoryStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return InMemoryEpisodeMemoryStore()

    @pytest.fixture
    def player_id(self):
        return PlayerId(1)

    def test_add_and_get_recent_returns_added_entry(self, store, player_id):
        """add したエピソードが get_recent で取得できる"""
        entry = _make_entry(eid="e1")
        store.add(player_id, entry)
        got = store.get_recent(player_id, 10)
        assert len(got) == 1
        assert got[0].id == "e1"
        assert got[0].context_summary == "洞窟にいた"

    def test_get_recent_empty_for_unknown_player(self, store):
        """未登録プレイヤーでは get_recent が空リストを返す"""
        got = store.get_recent(PlayerId(999), 5)
        assert got == []

    def test_get_recent_respects_limit(self, store, player_id):
        """get_recent の limit を超えない"""
        for i in range(5):
            store.add(
                player_id,
                _make_entry(eid=f"e{i}", ts=datetime.now() + timedelta(seconds=i)),
            )
        got = store.get_recent(player_id, 2)
        assert len(got) == 2

    def test_get_recent_since_filters_by_timestamp(self, store, player_id):
        """since を指定するとその時刻以降のみ返す"""
        base = datetime.now()
        store.add(player_id, _make_entry(eid="old", ts=base - timedelta(days=2)))
        store.add(player_id, _make_entry(eid="new", ts=base))
        got = store.get_recent(player_id, 10, since=base - timedelta(days=1))
        assert len(got) == 1
        assert got[0].id == "new"

    def test_add_many_adds_multiple_entries(self, store, player_id):
        """add_many で複数件追加できる"""
        entries = [
            _make_entry(eid="a1"),
            _make_entry(eid="a2"),
        ]
        store.add_many(player_id, entries)
        got = store.get_recent(player_id, 10)
        assert len(got) == 2

    def test_find_by_entities_and_actions_filters_by_entity(self, store, player_id):
        """find_by_entities_and_actions が entity_ids でフィルタする"""
        store.add(player_id, _make_entry(eid="e1", entity_ids=("chest_1", "loc_1")))
        store.add(player_id, _make_entry(eid="e2", entity_ids=("npc_1",)))
        got = store.find_by_entities_and_actions(
            player_id, entity_ids=["chest_1"], limit=10
        )
        assert len(got) == 1
        assert got[0].id == "e1"

    def test_find_by_entities_and_actions_filters_by_action(self, store, player_id):
        """find_by_entities_and_actions が action_taken でフィルタする"""
        store.add(
            player_id,
            _make_entry(eid="e1", action="open_chest を実行しました。"),
        )
        store.add(
            player_id,
            _make_entry(eid="e2", action="move_to_destination を実行しました。"),
        )
        got = store.find_by_entities_and_actions(
            player_id, action_names=["open_chest"], limit=10
        )
        assert len(got) == 1
        assert got[0].id == "e1"

    def test_increment_recall_count_increments(self, store, player_id):
        """increment_recall_count で recall_count が 1 増える"""
        entry = _make_entry(eid="e1", recall_count=0)
        store.add(player_id, entry)
        store.increment_recall_count(player_id, "e1")
        got = store.get_recent(player_id, 1)
        assert got[0].recall_count == 1

    def test_get_important_or_high_recall_returns_filtered(self, store, player_id):
        """get_important_or_high_recall が重要度・since でフィルタする"""
        base = datetime.now()
        store.add(
            player_id,
            _make_entry(eid="high", importance="high", ts=base),
        )
        store.add(
            player_id,
            _make_entry(eid="low", importance="low", ts=base),
        )
        got = store.get_important_or_high_recall(
            player_id, since=base - timedelta(days=1), min_importance="medium", limit=10
        )
        assert len(got) == 1
        assert got[0].id == "high"

    def test_get_important_or_high_recall_invalid_min_importance_raises_value_error(
        self, store, player_id
    ):
        """get_important_or_high_recall の min_importance が low/medium/high 以外のとき ValueError"""
        base = datetime.now()
        store.add(player_id, _make_entry(eid="e1", ts=base))
        with pytest.raises(ValueError, match="min_importance must be 'low', 'medium', or 'high'"):
            store.get_important_or_high_recall(
                player_id,
                since=base - timedelta(days=1),
                min_importance="invalid",
                limit=10,
            )

    def test_get_important_or_high_recall_negative_limit_raises_value_error(
        self, store, player_id
    ):
        """get_important_or_high_recall の limit が負のとき ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            store.get_important_or_high_recall(
                player_id,
                since=datetime.now() - timedelta(days=1),
                limit=-1,
            )

    def test_add_player_id_none_raises_type_error(self, store):
        """add に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.add(None, _make_entry())  # type: ignore[arg-type]

    def test_add_entry_not_episode_memory_entry_raises_type_error(
        self, store, player_id
    ):
        """add に entry が EpisodeMemoryEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be EpisodeMemoryEntry"):
            store.add(player_id, "invalid")  # type: ignore[arg-type]

    def test_add_many_entries_not_list_raises_type_error(self, store, player_id):
        """add_many に entries が list でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must be list"):
            store.add_many(player_id, "not a list")  # type: ignore[arg-type]

    def test_add_many_entries_contain_non_entry_raises_type_error(
        self, store, player_id
    ):
        """add_many の要素が EpisodeMemoryEntry でないとき TypeError"""
        with pytest.raises(
            TypeError, match="entries must contain only EpisodeMemoryEntry"
        ):
            store.add_many(player_id, [_make_entry(), "invalid"])  # type: ignore[list-item]

    def test_get_recent_negative_limit_raises_value_error(self, store, player_id):
        """get_recent の limit が負で ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            store.get_recent(player_id, -1)

    def test_get_recent_since_not_datetime_raises_type_error(self, store, player_id):
        """get_recent の since が datetime でないとき TypeError"""
        with pytest.raises(TypeError, match="since must be datetime or None"):
            store.get_recent(player_id, 10, since="invalid")  # type: ignore[arg-type]

    def test_find_by_entities_player_id_none_raises_type_error(self, store):
        """find_by_entities_and_actions に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            store.find_by_entities_and_actions(None, limit=10)  # type: ignore[arg-type]

    def test_increment_recall_count_unknown_episode_id_does_not_raise(
        self, store, player_id
    ):
        """存在しない episode_id で increment_recall_count を呼んでも例外にならない"""
        store.add(player_id, _make_entry(eid="e1"))
        store.increment_recall_count(player_id, "nonexistent")
        got = store.get_recent(player_id, 1)
        assert got[0].recall_count == 0

    def test_find_by_entities_and_actions_filters_by_scope_keys(
        self, store, player_id
    ):
        """find_by_entities_and_actions が scope_keys でフィルタする（関係性メモリ検索契約）"""
        store.add(
            player_id,
            _make_entry(eid="e_quest", scope_keys=("quest:1",)),
        )
        store.add(
            player_id,
            _make_entry(eid="e_guild", scope_keys=("guild:3",)),
        )
        store.add(
            player_id,
            _make_entry(eid="e_noscope", scope_keys=()),
        )
        got = store.find_by_entities_and_actions(
            player_id, scope_keys=["quest:1"], limit=10
        )
        assert len(got) == 1
        assert got[0].id == "e_quest"
