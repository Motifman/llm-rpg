"""MemoryLink / セマンティック SQLite ストアの roundtrip と署名登録。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.contracts.episodic_memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.application.llm.contracts.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import SqliteMemoryLinkStore
from ai_rpg_world.infrastructure.repository.sqlite_semantic_memory_store import SqliteSemanticMemoryStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    default_link_and_semantic_stores_for_episode_store,
)
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "episodic_graph.sqlite"


def test_sqlite_memory_link_roundtrip_and_weakest_removal(db_path: Path) -> None:
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    store = SqliteMemoryLinkStore(episode_store.connection)
    now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    ln = MemoryLink(
        link_id="memlink-test-1",
        player_id=1,
        episode_id_a="a",
        episode_id_b="z",
        link_type=MemoryLinkType.TEMPORAL,
        strength=0.9,
        co_activation_count=1,
        created_at=now,
        last_activated_at=now,
        decay_rate=0.1,
    )
    store.upsert_link(ln)
    got = store.get_link(1, "z", "a", MemoryLinkType.TEMPORAL)
    assert got is not None
    assert got.link_id == ln.link_id
    assert got.episode_id_a == "a" and got.episode_id_b == "z"

    weak = MemoryLink(
        link_id="memlink-test-2",
        player_id=1,
        episode_id_a="a",
        episode_id_b="m",
        link_type=MemoryLinkType.TEMPORAL,
        strength=0.01,
        co_activation_count=1,
        created_at=now,
        last_activated_at=now,
        decay_rate=0.1,
    )
    store.upsert_link(weak)
    assert store.count_links_for_episode(1, "a") == 2
    removed = store.remove_weakest_link_for_episode(1, "a", now=now)
    assert removed is True
    assert store.count_links_for_episode(1, "a") == 1
    assert store.get_link(1, "a", "m", MemoryLinkType.TEMPORAL) is None

    # 再接続しても残る
    episode_store2 = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    store2 = SqliteMemoryLinkStore(episode_store2.connection)
    assert store2.get_link(1, "a", "z", MemoryLinkType.TEMPORAL) is not None


def test_default_link_semantic_factory_uses_sqlite_when_episode_is_sqlite(
    db_path: Path,
) -> None:
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    ls, sem = default_link_and_semantic_stores_for_episode_store(episode_store)
    assert isinstance(ls, SqliteMemoryLinkStore)
    assert isinstance(sem, SqliteSemanticMemoryStore)


def test_default_link_semantic_factory_in_memory_when_episode_in_memory() -> None:
    ls, sem = default_link_and_semantic_stores_for_episode_store(InMemorySubjectiveEpisodeStore())
    assert isinstance(ls, InMemoryMemoryLinkStore)
    assert isinstance(sem, InMemorySemanticMemoryStore)


def test_sqlite_semantic_signature_and_entries(db_path: Path) -> None:
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    sem = SqliteSemanticMemoryStore(episode_store.connection)
    assert sem.register_cluster_signature_if_new(1, "sig-a") is True
    assert sem.register_cluster_signature_if_new(1, "sig-a") is False
    now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    entry = SemanticMemoryEntry(
        entry_id="sem-1",
        player_id=1,
        text="hello",
        evidence_episode_ids=("e1", "e2"),
        confidence=0.8,
        created_at=now,
    )
    sem.add(entry)
    rows = sem.list_for_player(1)
    assert len(rows) == 1
    assert rows[0].entry_id == "sem-1"
    assert rows[0].evidence_episode_ids == ("e1", "e2")
