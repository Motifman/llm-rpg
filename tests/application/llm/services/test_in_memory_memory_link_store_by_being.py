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

    def test_new_upsert_get_can_get(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """新規 upsert は get で取得できる。"""
        link = _link(episode_id_a="a", episode_id_b="b")
        store.upsert_link_by_being(being, link)
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None
        assert got.episode_id_a == "a"
        assert got.episode_id_b == "b"

    def test_same_key_upsert(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """同一 key の upsert は上書き。"""
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.5))
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b", strength=0.9))
        got = store.get_link_by_being(being, "a", "b", MemoryLinkType.CO_RECALL)
        assert got is not None and got.strength == pytest.approx(0.9)

    def test_episode_pair(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """a,b と b,a は同一リンク。"""
        store.upsert_link_by_being(being, _link(episode_id_a="a", episode_id_b="b"))
        got = store.get_link_by_being(being, "b", "a", MemoryLinkType.CO_RECALL)
        assert got is not None

    def test_being_id_raises_type_error(
        self, store: InMemoryMemoryLinkStore
    ) -> None:
        """being id 型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.upsert_link_by_being(
                "not-a-being-id",  # type: ignore[arg-type]
                _link(episode_id_a="a", episode_id_b="b"),
            )


class TestListAndCountByBeing:
    """``list_links_for_episode_by_being`` / ``list_all_incident_links_by_being`` /
    ``count_links_for_episode_by_being`` の挙動。"""

    def test_returns_all_episode_link(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """episode に接続する link を全件返す。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="z"))
        store.upsert_link_by_being(being, _link(episode_id_a="y", episode_id_b="z"))
        # x に接続するのは 2 件
        result = store.list_all_incident_links_by_being(being, "x", now=_NOW)
        assert len(result) == 2

    def test_returns_count(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """count も接続数を返す。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="z"))
        assert store.count_links_for_episode_by_being(being, "x") == 2
        assert store.count_links_for_episode_by_being(being, "y") == 1

    def test_list_links_episode_strength_limit(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """list links for episode は strength 降順で limit 適用。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="a", strength=0.3))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="b", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="c", strength=0.6))
        result = store.list_links_for_episode_by_being(being, "x", now=_NOW, limit=2)
        assert len(result) == 2
        assert {r.episode_id_b for r in result if r.episode_id_a == "x"} | {
            r.episode_id_a for r in result if r.episode_id_b == "x"
        } >= {"b", "c"}  # 強い 2 件 (b=0.9, c=0.6) が選ばれる

    def test_limit_zero_less_empty_list(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """limit 0 以下は 空 list。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        assert store.list_links_for_episode_by_being(being, "x", now=_NOW, limit=0) == []


class TestRemoveWeakestByBeing:
    """``remove_weakest_link_for_episode_by_being`` の挙動。"""

    def test_link_deleted(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """最弱 link が削除される。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="strong", strength=0.9))
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="weak", strength=0.1))
        removed = store.remove_weakest_link_for_episode_by_being(being, "x", now=_NOW)
        assert removed is True
        # strong は残り、weak は消える
        remaining = store.list_all_incident_links_by_being(being, "x", now=_NOW)
        assert len(remaining) == 1
        assert "weak" not in (remaining[0].episode_id_a, remaining[0].episode_id_b)

    def test_link_false(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """該当 link が無ければ False。"""
        assert (
            store.remove_weakest_link_for_episode_by_being(being, "nope", now=_NOW)
            is False
        )


class TestListAllForBeing:
    """``list_all_links_for_being``: 当該 Being の全リンク。"""

    def test_returns_all_items(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """全件返す。"""
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(being, _link(episode_id_a="y", episode_id_b="z"))
        all_links = store.list_all_links_for_being(being)
        assert len(all_links) == 2

    def test_other_being_link_not_rendered(
        self, store: InMemoryMemoryLinkStore, being: BeingId
    ) -> None:
        """他 Being の link は出ない。"""
        other = BeingId("being_w1_p2")
        store.upsert_link_by_being(being, _link(episode_id_a="x", episode_id_b="y"))
        store.upsert_link_by_being(other, _link(episode_id_a="x", episode_id_b="z"))
        assert len(store.list_all_links_for_being(being)) == 1
        assert len(store.list_all_links_for_being(other)) == 1


class TestReplaceAllByBeing:
    """replace_all_by_being の挙動 (Phase 4 Step 4-2a, snapshot restore primitive)。"""

    def test_replace_all_replaces_existing_links(self, store: InMemoryMemoryLinkStore) -> None:
        """既存 link を一括置換できる。"""
        b = BeingId("ada")
        old = _link(episode_id_a="ep-1", episode_id_b="ep-2")
        store.upsert_link_by_being(b, old)
        new = _link(episode_id_a="ep-3", episode_id_b="ep-4")
        store.replace_all_by_being(b, [new])
        all_links = store.list_all_links_for_being(b)
        assert len(all_links) == 1
        assert all_links[0].episode_id_a == "ep-3"

    def test_empty_list_all_can_delete(self, store: InMemoryMemoryLinkStore) -> None:
        """空リストで全削除できる。"""
        b = BeingId("ada")
        store.upsert_link_by_being(
            b, _link(episode_id_a="ep-1", episode_id_b="ep-2")
        )
        store.replace_all_by_being(b, [])
        assert store.list_all_links_for_being(b) == []

    def test_other_being_link_does_not_affect(self, store: InMemoryMemoryLinkStore) -> None:
        """他 being の link は影響しない。"""
        store.upsert_link_by_being(
            BeingId("ada"), _link(episode_id_a="ep-1", episode_id_b="ep-2")
        )
        store.upsert_link_by_being(
            BeingId("ben"), _link(episode_id_a="ep-3", episode_id_b="ep-4")
        )
        store.replace_all_by_being(BeingId("ada"), [])
        assert len(store.list_all_links_for_being(BeingId("ben"))) == 1

    def test_replace_after_episode_index_via_can_lookup(
        self, store: InMemoryMemoryLinkStore
    ) -> None:
        """list_links_for_episode_by_being が replace 後も整合する。"""
        b = BeingId("ada")
        store.replace_all_by_being(
            b, [_link(episode_id_a="ep-X", episode_id_b="ep-Y")]
        )
        results = store.list_links_for_episode_by_being(
            b, "ep-X", now=_NOW, limit=10
        )
        assert len(results) == 1


# Phase 3 Step 3c-3 (Issue #470): legacy player_id 版 API が撤去されたため、
# 旧/新 API の独立性を検証していたテストクラス ``TestIndependenceFromPlayerIdApi``
# は削除された。新 API のみが残り、being_id を一次キーとして扱う設計に統一。
