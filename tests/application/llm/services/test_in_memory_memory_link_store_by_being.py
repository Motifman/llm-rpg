"""``InMemoryMemoryLinkStore`` の being_id 版 API テスト (Phase 3 Step 3c-1)。

並走追加された ``*_by_being`` メソッド群が legacy player_id 版と互いに見え
ないことと、各メソッドが期待通り動くことを確認する。memo / semantic の
並走追加 PR と同じパターン。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


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


@pytest.fixture
def store() -> InMemoryMemoryLinkStore:
    return InMemoryMemoryLinkStore()


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestUpsertAndGetByBeing:
    """``upsert_link_by_being`` / ``get_link_by_being`` の基本挙動。"""

    def test_新規_upsert_は_get_で_取得できる(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        link = _link(episode_id_a="a", episode_id_b="b")
        store.upsert_link_by_being(being, link)
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None
        assert got.episode_id_a == "a"
        assert got.episode_id_b == "b"

    def test_同一_key_の_upsert_は_上書き(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.5))
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.9))
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None and got.strength == pytest.approx(0.9)

    def test_episode_pair_は_正規化される(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """a,b と b,a は同一リンク。"""
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b"))
        got = store.get_link_by_being(being, "b", "a", MemoryLinkType.CO_RECALL)
        assert got is not None

    def test_being_id_型違反は_TypeError(
        self, store: InMemoryMemoryLinkStore
    ) -> None:
        with pytest.raises(TypeError, match="being_id"):
            store.upsert_link_by_being(
                "not-a-being-id",  # type: ignore[arg-type]
                _link(episode_id_a="a", episode_id_b="b"),
            )


class TestListAndCountByBeing:
    """``list_links_for_episode_by_being`` / ``list_all_incident_links_by_being`` /
    ``count_links_for_episode_by_being`` の挙動。"""

    def test_episode_に_接続する_link_を_全件返す(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="z"))
        store.upsert_link_by_being(being, _link(episode_id_a="y", episode_id_b="z"))
        # x に接続するのは 2 件
        result = store.list_all_incident_links_by_being(being, "x", now=_NOW)
        assert len(result) == 2

    def test_count_も_接続数を返す(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="z"))
        assert store.count_links_for_episode_by_being(being, "x") == 2
        assert store.count_links_for_episode_by_being(being, "y") == 1

    def test_list_links_for_episode_は_strength_降順で_limit_適用(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="a", strength=0.3))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="b", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="c", strength=0.6))
        result = store.list_links_for_episode_by_being(being, "x", now=_NOW, limit=2)
        assert len(result) == 2
        assert {r.episode_id_b for r in result if r.episode_id_a == "x"} | {
            r.episode_id_a for r in result if r.episode_id_b == "x"
        } >= {"b", "c"}  # 強い 2 件 (b=0.9, c=0.6) が選ばれる

    def test_limit_0_以下は_空_list(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        assert store.list_links_for_episode_by_being(being, "x", now=_NOW, limit=0) == []


class TestRemoveWeakestByBeing:
    """``remove_weakest_link_for_episode_by_being`` の挙動。"""

    def test_最弱_link_が_削除される(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="strong", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="weak", strength=0.1))
        removed = store.remove_weakest_link_for_episode_by_being(being, "x", now=_NOW)
        assert removed is True
        # strong は残り、weak は消える
        remaining = store.list_all_incident_links_by_being(being, "x", now=_NOW)
        assert len(remaining) == 1
        assert "weak" not in (remaining[0].episode_id_a, remaining[0].episode_id_b)

    def test_該当_link_が_無ければ_False(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        assert (
            store.remove_weakest_link_for_episode_by_being(being, "nope", now=_NOW)
            is False
        )


class TestListAllForBeing:
    """``list_all_links_for_being``: 当該 Being の全リンク。"""

    def test_全件返す(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="y", episode_id_b="z"))
        all_links = store.list_all_links_for_being(being)
        assert len(all_links) == 2

    def test_他_Being_の_link_は_出ない(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        other = BeingId("being_w1_p2")
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(other, _link(episode_id_a="x", episode_id_b="z"))
        assert len(store.list_all_links_for_being(being)) == 1
        assert len(store.list_all_links_for_being(other)) == 1


class TestIndependenceFromPlayerIdApi:
    """新旧 API の独立性 (= 並走 index は同期しない)。"""

    def test_player_id_経由で追加した_link_は_being_id_経由では見えない(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link(_link(episode_id_a="a", episode_id_b="b", player_id=1))
        assert store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL) is None
        assert store.list_all_links_for_being(being) == []

    def test_being_id_経由で追加した_link_は_player_id_経由では見えない(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", player_id=1))
        assert (
            store.get_link(1, "a", "b", MemoryLinkType.CO_RECALL) is None
        )
        assert store.list_all_links_for_player(1) == []
