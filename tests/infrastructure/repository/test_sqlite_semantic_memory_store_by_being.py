"""SqliteSemanticMemoryStore の being_id 版 API 挙動 (Phase 3 Step 3b-1)。

schema v2 (= semantic_memory_entries_by_being / semantic_cluster_signatures_by_being)
への永続化を確認する。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.infrastructure.repository.sqlite_semantic_memory_store import (
    SqliteSemanticMemoryStore,
)


def _make_entry(
    entry_id: str = "e1",
    player_id: int = 1,
    text: str = "アダは図書館で本を借りた",
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=player_id,
        text=text,
        evidence_episode_ids=("ep-1", "ep-2"),
        confidence=0.7,
        created_at=datetime.now(timezone.utc),
        importance_score=8,
        tags=("library", "book"),
    )


@pytest.fixture
def store() -> SqliteSemanticMemoryStore:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return SqliteSemanticMemoryStore(conn)


class TestSqliteSemanticByBeingRoundtrip:
    """add_by_being → list_for_being のラウンドトリップ。"""

    def test_保存して取り出せる(self, store: SqliteSemanticMemoryStore) -> None:
        """add → list で同等の entry が返る。"""
        being_id = BeingId("ada")
        entry = _make_entry()
        store.add_by_being(being_id, entry)
        result = store.list_for_being(being_id)
        assert len(result) == 1
        loaded = result[0]
        assert loaded.entry_id == entry.entry_id
        assert loaded.text == entry.text
        assert loaded.evidence_episode_ids == entry.evidence_episode_ids
        assert loaded.confidence == entry.confidence
        assert loaded.importance_score == entry.importance_score
        assert loaded.tags == entry.tags
        assert loaded.player_id == entry.player_id

    def test_同一_entry_id_は_upsert_される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        """同 (being_id, entry_id) は ON CONFLICT で上書きされる。"""
        being_id = BeingId("ada")
        store.add_by_being(being_id, _make_entry(text="v1"))
        store.add_by_being(being_id, _make_entry(text="v2"))
        result = store.list_for_being(being_id)
        assert len(result) == 1
        assert result[0].text == "v2"

    def test_異なる_being_id_の_entry_は独立に保持(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        """同じ entry_id でも being_id が違えば PK が違うので独立保持。"""
        store.add_by_being(BeingId("ada"), _make_entry(entry_id="e1", text="ada"))
        store.add_by_being(BeingId("ben"), _make_entry(entry_id="e1", text="ben"))
        assert store.list_for_being(BeingId("ada"))[0].text == "ada"
        assert store.list_for_being(BeingId("ben"))[0].text == "ben"

    def test_未登録_being_には空リスト(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        """未登録 being_id は空リスト。"""
        assert store.list_for_being(BeingId("nobody")) == []

    def test_created_at_降順で返る(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        """list_for_being は created_at DESC で並ぶ。"""
        being_id = BeingId("ada")
        store.add_by_being(
            being_id,
            SemanticMemoryEntry(
                entry_id="old",
                player_id=1,
                text="先",
                evidence_episode_ids=("ep",),
                confidence=0.5,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )
        store.add_by_being(
            being_id,
            SemanticMemoryEntry(
                entry_id="new",
                player_id=1,
                text="後",
                evidence_episode_ids=("ep",),
                confidence=0.5,
                created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            ),
        )
        result = store.list_for_being(being_id)
        assert [e.entry_id for e in result] == ["new", "old"]


class TestSqliteClusterSignatureByBeing:
    """register_cluster_signature_if_new_by_being の永続化挙動。"""

    def test_初回_True_既存_False(self, store: SqliteSemanticMemoryStore) -> None:
        assert (
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), "sig-1"
            )
            is True
        )
        assert (
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), "sig-1"
            )
            is False
        )

    def test_異なる_being_id_なら独立に登録(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        """異なる being_id 同 signature は両方登録される。"""
        assert (
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), "sig-x"
            )
            is True
        )
        assert (
            store.register_cluster_signature_if_new_by_being(
                BeingId("ben"), "sig-x"
            )
            is True
        )


class TestSqliteSemanticTypeGuards:
    """型違反の弾き方。"""

    def test_add_by_being_の型違反(self, store: SqliteSemanticMemoryStore) -> None:
        with pytest.raises(TypeError, match="being_id"):
            store.add_by_being("ada", _make_entry())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="entry"):
            store.add_by_being(BeingId("ada"), "not-an-entry")  # type: ignore[arg-type]

    def test_list_for_being_の型違反(self, store: SqliteSemanticMemoryStore) -> None:
        with pytest.raises(TypeError):
            store.list_for_being("ada")  # type: ignore[arg-type]

    def test_signature_の型違反(self, store: SqliteSemanticMemoryStore) -> None:
        with pytest.raises(TypeError, match="evidence_signature"):
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), 123  # type: ignore[arg-type]
            )


class TestSqliteSemanticReplaceAll:
    """Phase 4 Step 4-2a: replace_all_by_being の挙動 (snapshot restore primitive)。"""

    def test_既存_entries_と_signatures_を一括置換する(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        b = BeingId("ada")
        store.add_by_being(b, _make_entry("old"))
        store.register_cluster_signature_if_new_by_being(b, "sig-old")
        new = _make_entry("new")
        store.replace_all_by_being(b, [new], ["sig-new"])
        ids = [e.entry_id for e in store.list_for_being(b)]
        assert ids == ["new"]
        assert store.list_cluster_signatures_by_being(b) == ["sig-new"]

    def test_他_being_の状態は影響を受けない(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        store.add_by_being(BeingId("ada"), _make_entry("a1"))
        store.register_cluster_signature_if_new_by_being(BeingId("ada"), "sig-a")
        store.add_by_being(BeingId("ben"), _make_entry("b1"))
        store.register_cluster_signature_if_new_by_being(BeingId("ben"), "sig-b")
        store.replace_all_by_being(BeingId("ada"), [], [])
        ids = [e.entry_id for e in store.list_for_being(BeingId("ben"))]
        assert ids == ["b1"]
        assert store.list_cluster_signatures_by_being(BeingId("ben")) == ["sig-b"]

    def test_list_cluster_signatures_は_辞書順(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        b = BeingId("ada")
        store.register_cluster_signature_if_new_by_being(b, "z")
        store.register_cluster_signature_if_new_by_being(b, "a")
        assert store.list_cluster_signatures_by_being(b) == ["a", "z"]


# Phase 3 Step 3b-3 (Issue #470): legacy player_id 版テーブルは schema v3 で
# DROP され、対応する API も撤去された。新旧テーブルの独立性を検証していた
# ``TestSqliteSemanticParallelTablesIndependence`` は削除された。schema レベルで
# legacy テーブルが消えていることは
# ``tests/infrastructure/repository/test_sqlite_memory_graph_stores.py::
# test_sqlite_legacy_semantic_tables_are_dropped`` でカバーされる。
