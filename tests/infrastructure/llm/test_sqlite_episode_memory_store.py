"""SqliteEpisodeMemoryStore のテスト（永続化・scope_keys 検索）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
    SqliteEpisodeMemoryStore,
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
    world_object_ids: tuple = (),
    spot_id_value: int | None = None,
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
        world_object_ids=world_object_ids,
        spot_id_value=spot_id_value,
    )


class TestSqliteEpisodeMemoryStore:
    """SqliteEpisodeMemoryStore の永続化・契約テスト"""

    def test_add_and_get_recent_persists_across_store_recreation(self, tmp_path):
        """add したエピソードがストア再作成後も get_recent で取得できる"""
        db_path = tmp_path / "episode.db"
        store = SqliteEpisodeMemoryStore(db_path)
        player_id = PlayerId(1)
        entry = _make_entry(eid="e1", context="洞窟で冒険した")
        store.add(player_id, entry)

        store2 = SqliteEpisodeMemoryStore(db_path)
        got = store2.get_recent(player_id, 10)
        assert len(got) == 1
        assert got[0].id == "e1"
        assert got[0].context_summary == "洞窟で冒険した"

    def test_scope_keys_persisted_and_retrievable(self, tmp_path):
        """scope_keys が永続化され、find_by_entities_and_actions で scope_keys 検索できる"""
        db_path = tmp_path / "episode.db"
        store = SqliteEpisodeMemoryStore(db_path)
        player_id = PlayerId(1)
        store.add(
            player_id,
            _make_entry(eid="e_quest", scope_keys=("quest:1",)),
        )
        store.add(
            player_id,
            _make_entry(eid="e_guild", scope_keys=("guild:3",)),
        )
        got = store.find_by_entities_and_actions(
            player_id, scope_keys=["quest:1"], limit=10
        )
        assert len(got) == 1
        assert got[0].id == "e_quest"
        assert "quest:1" in got[0].scope_keys

    def test_increment_recall_count_persists(self, tmp_path):
        """increment_recall_count の結果が永続化される"""
        db_path = tmp_path / "episode.db"
        store = SqliteEpisodeMemoryStore(db_path)
        player_id = PlayerId(1)
        store.add(player_id, _make_entry(eid="e1", recall_count=0))
        store.increment_recall_count(player_id, "e1")
        store2 = SqliteEpisodeMemoryStore(db_path)
        got = store2.get_recent(player_id, 1)
        assert got[0].recall_count == 1
