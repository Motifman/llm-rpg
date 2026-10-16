"""MemoryLink SQLite ストアの roundtrip と、memory graph スキーマが古い表を消すこと。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import InMemoryMemoryLinkStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    default_link_store_for_episode_store,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import SqliteMemoryLinkStore
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import SqliteSubjectiveEpisodeStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / 'episodic_graph.sqlite'

def test_sqlite_memory_link_roundtrip_and_weakest_removal(db_path: Path) -> None:
    """Phase 3 Step 3c-3: being_id keyed only。"""
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    store = SqliteMemoryLinkStore(episode_store.connection)
    being_id = BeingId('being_w1_p1')
    now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    ln = MemoryLink(link_id='memlink-test-1', player_id=1, being_id=being_id, episode_id_a='a', episode_id_b='z', link_type=MemoryLinkType.TEMPORAL, strength=0.9, co_activation_count=1, created_at=now, last_activated_at=now, decay_rate=0.1)
    store.upsert_link_by_being(being_id, ln)
    got = store.get_link_by_being(being_id, 'z', 'a', MemoryLinkType.TEMPORAL)
    assert got is not None
    assert got.link_id == ln.link_id
    assert got.episode_id_a == 'a' and got.episode_id_b == 'z'
    weak = MemoryLink(link_id='memlink-test-2', player_id=1, being_id=being_id, episode_id_a='a', episode_id_b='m', link_type=MemoryLinkType.TEMPORAL, strength=0.01, co_activation_count=1, created_at=now, last_activated_at=now, decay_rate=0.1)
    store.upsert_link_by_being(being_id, weak)
    assert store.count_links_for_episode_by_being(being_id, 'a') == 2
    removed = store.remove_weakest_link_for_episode_by_being(being_id, 'a', now=now)
    assert removed is True
    assert store.count_links_for_episode_by_being(being_id, 'a') == 1
    assert store.get_link_by_being(being_id, 'a', 'm', MemoryLinkType.TEMPORAL) is None
    episode_store2 = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    store2 = SqliteMemoryLinkStore(episode_store2.connection)
    assert store2.get_link_by_being(being_id, 'a', 'z', MemoryLinkType.TEMPORAL) is not None
    inc_a = store.list_all_incident_links_by_being(being_id, 'a', now=now)
    assert len(inc_a) == 1
    assert inc_a[0].link_id == ln.link_id

def test_sqlite_legacy_memory_links_table_is_dropped(db_path: Path) -> None:
    """Phase 3 Step 3c-3: schema v5 で legacy ``memory_links`` テーブルが
    DROP されていること。"""
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    SqliteMemoryLinkStore(episode_store.connection)
    conn = episode_store.connection
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row['name'] for row in rows}
    assert 'memory_links' not in table_names

def test_default_link_factory_uses_sqlite_when_episode_is_sqlite(db_path: Path) -> None:
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    assert isinstance(default_link_store_for_episode_store(episode_store), SqliteMemoryLinkStore)

def test_default_link_factory_in_memory_when_episode_in_memory() -> None:
    assert isinstance(default_link_store_for_episode_store(InMemorySubjectiveEpisodeStore()), InMemoryMemoryLinkStore)

def test_sqlite_legacy_semantic_tables_are_dropped(db_path: Path) -> None:
    """Phase 3 Step 3b-3: schema v3 で legacy テーブルが完全に消えていること。"""
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    SqliteMemoryLinkStore(episode_store.connection)
    conn = episode_store.connection
    legacy_tables = {'semantic_memory_entries', 'semantic_cluster_signatures'}
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row['name'] for row in rows}
    assert legacy_tables.isdisjoint(table_names), f'legacy table 残存: {legacy_tables & table_names}'
