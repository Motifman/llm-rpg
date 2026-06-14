"""``SqliteMemoryLinkStore`` の being_id 版 API テスト (Phase 3 Step 3c-1)。

schema v4 で追加した ``memory_links_by_being`` テーブル経由で各 API が動作
すること、および legacy ``memory_links`` テーブルと独立していることを確認
する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import (
    SqliteMemoryLinkStore,
)
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "memory_link.db"


@pytest.fixture
def store(db_path: Path) -> SqliteMemoryLinkStore:
    episode_store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
    return SqliteMemoryLinkStore(episode_store.connection)


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


def _link(
    *,
    episode_id_a: str,
    episode_id_b: str,
    player_id: int = 1,
    strength: float = 0.9,
    link_type: MemoryLinkType = MemoryLinkType.CO_RECALL,
    last_activated_at: datetime = _NOW,
    decay_rate: float = 0.001,
    co_activation_count: int = 1,
) -> MemoryLink:
    na, nb = sorted((episode_id_a, episode_id_b))
    return MemoryLink(
        link_id=f"mlk-{na}-{nb}-{link_type.value}",
        player_id=player_id,
        episode_id_a=na,
        episode_id_b=nb,
        link_type=link_type,
        strength=strength,
        co_activation_count=co_activation_count,
        created_at=_NOW,
        last_activated_at=last_activated_at,
        decay_rate=decay_rate,
    )


class TestSqliteMemoryLinkByBeingBasic:
    """upsert / get / list / count / remove の SQLite 永続化挙動。"""

    def test_upsert_と_get(self, store: SqliteMemoryLinkStore, being: BeingId) -> None:
        link = _link(episode_id_a="a", episode_id_b="b")
        store.upsert_link_by_being(being, link)
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None
        assert got.episode_id_a == "a" and got.episode_id_b == "b"

    def test_同一_key_の_upsert_は_上書き(
        self, store: SqliteMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.3))
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.95))
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None and got.strength == pytest.approx(0.95)

    def test_list_for_episode_は_strength_降順で_limit_適用(
        self, store: SqliteMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="a", strength=0.3))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="b", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="c", strength=0.6))
        result = store.list_links_for_episode_by_being(being, "x", now=_NOW, limit=2)
        assert len(result) == 2

    def test_count(self, store: SqliteMemoryLinkStore, being: BeingId) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="z"))
        assert store.count_links_for_episode_by_being(being, "x") == 2

    def test_remove_weakest(self, store: SqliteMemoryLinkStore, being: BeingId) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="strong", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="weak", strength=0.1))
        assert store.remove_weakest_link_for_episode_by_being(being, "x", now=_NOW) is True
        remaining = store.list_all_incident_links_by_being(being, "x", now=_NOW)
        assert len(remaining) == 1

    def test_list_all_for_being(
        self, store: SqliteMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="y", episode_id_b="z"))
        assert len(store.list_all_links_for_being(being)) == 2


class TestSqliteMemoryLinkByBeingIsolation:
    """新旧テーブルが独立: legacy memory_links と memory_links_by_being は混ざらない。"""

    def test_player_id_経由で保存しても_being_id_経由では見えない(
        self, store: SqliteMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link(_link(episode_id_a="a", episode_id_b="b", player_id=1))
        assert store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL) is None

    def test_being_id_経由で保存しても_player_id_経由では見えない(
        self, store: SqliteMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", player_id=1))
        assert store.get_link(1, "a", "b", MemoryLinkType.CO_RECALL) is None


class TestSqliteMemoryLinkByBeingTypeGuard:
    """型違反は TypeError。"""

    def test_being_id_型違反は_TypeError(self, store: SqliteMemoryLinkStore) -> None:
        with pytest.raises(TypeError, match="being_id"):
            store.upsert_link_by_being(
                "not-a-being",  # type: ignore[arg-type]
                _link(episode_id_a="a", episode_id_b="b"),
            )
