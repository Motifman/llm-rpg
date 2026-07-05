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


class TestSqliteSemanticBeliefJournalRoundtrip:
    """U3a: belief journal フィールドの永続化 round-trip。"""

    def test_belief_journal_フィールドが永続化される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        being_id = BeingId("ada")
        entry = SemanticMemoryEntry(
            entry_id="e1",
            player_id=1,
            text="ノアは機嫌が悪いと無視する",
            evidence_episode_ids=("ep-1",),
            confidence=0.7,
            created_at=datetime.now(timezone.utc),
            belief_id="belief-noah-mood",
            status="active",
            supersedes="e0",
            support_evidence_ids=("ev-1", "ev-2"),
            contradict_evidence_ids=("ev-3",),
        )
        store.add_by_being(being_id, entry)
        loaded = store.list_for_being(being_id)[0]
        assert loaded.belief_id == "belief-noah-mood"
        assert loaded.status == "active"
        assert loaded.supersedes == "e0"
        assert loaded.support_evidence_ids == ("ev-1", "ev-2")
        assert loaded.contradict_evidence_ids == ("ev-3",)


class TestSqliteSupersedeByBeing:
    """supersede_by_being の永続化挙動 (U3a)。"""

    def test_old_が_superseded_new_が_active_で保存される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        being_id = BeingId("ada")
        old = _make_entry("old", text="拠点に資源はない")
        store.add_by_being(being_id, old)
        new = SemanticMemoryEntry(
            entry_id="new",
            player_id=1,
            text="拠点に資源が見つかることがある",
            evidence_episode_ids=("ep-3",),
            confidence=0.7,
            created_at=datetime.now(timezone.utc),
            belief_id=old.belief_id,
            supersedes="old",
        )
        store.supersede_by_being(being_id, old_entry_id="old", new_entry=new)

        entries = {e.entry_id: e for e in store.list_for_being(being_id)}
        assert entries["old"].status == "superseded"
        assert entries["new"].status == "active"
        assert entries["new"].supersedes == "old"
        assert entries["new"].belief_id == old.belief_id

    def test_old_entry_id_が存在しなくても_new_entry_は追加される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        being_id = BeingId("ada")
        new = _make_entry("new")
        store.supersede_by_being(
            being_id, old_entry_id="does-not-exist", new_entry=new
        )
        assert [e.entry_id for e in store.list_for_being(being_id)] == ["new"]

    def test_型違反は_TypeError(self, store: SqliteSemanticMemoryStore) -> None:
        with pytest.raises(TypeError, match="being_id"):
            store.supersede_by_being(
                "ada", old_entry_id="old", new_entry=_make_entry()  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="new_entry"):
            store.supersede_by_being(
                BeingId("ada"), old_entry_id="old", new_entry="not-an-entry"  # type: ignore[arg-type]
            )


class TestSqliteUpdateStatusByBeing:
    """update_status_by_being の永続化挙動 (U3a)。"""

    def test_指定_entry_の_status_が更新される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        being_id = BeingId("ada")
        store.add_by_being(being_id, _make_entry("e1"))
        store.update_status_by_being(being_id, "e1", "inactive")
        assert store.list_for_being(being_id)[0].status == "inactive"

    def test_存在しない_entry_id_は無視される(
        self, store: SqliteSemanticMemoryStore
    ) -> None:
        being_id = BeingId("ada")
        store.add_by_being(being_id, _make_entry("e1"))
        store.update_status_by_being(being_id, "does-not-exist", "inactive")
        assert store.list_for_being(being_id)[0].status == "active"


class TestSqliteSemanticBackwardCompatOldSchema:
    """U3a: belief journal カラム追加前の旧 DB を開いても後方互換に読める。

    schema v5 (belief journal カラム無し) 相当の DB を素の SQL で作り、
    ``SqliteSemanticMemoryStore`` で開いてマイグレーション (v6) を走らせた後、
    旧行が default 値 (belief_id 空文字→entry_id フォールバック, status="active")
    で読めることを確認する。
    """

    def test_旧スキーマの行が_default_値で読める(self) -> None:
        from ai_rpg_world.infrastructure.repository.sqlite_migration import (
            SqliteMigration,
            apply_migrations,
        )
        from ai_rpg_world.infrastructure.repository.sqlite_memory_graph_schema import (
            _MEMORY_GRAPH_SCHEMA_NAMESPACE,
            _init_memory_graph_v1,
            _init_memory_graph_v2_semantic_by_being,
            _init_memory_graph_v3_drop_legacy_semantic,
            _init_memory_graph_v4_memory_link_by_being,
            _init_memory_graph_v5_drop_legacy_memory_links,
        )

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # v6 (belief journal カラム) 未適用の状態を素の SQL で再現する。
        apply_migrations(
            conn,
            namespace=_MEMORY_GRAPH_SCHEMA_NAMESPACE,
            migrations=[
                SqliteMigration(1, _init_memory_graph_v1),
                SqliteMigration(2, _init_memory_graph_v2_semantic_by_being),
                SqliteMigration(3, _init_memory_graph_v3_drop_legacy_semantic),
                SqliteMigration(4, _init_memory_graph_v4_memory_link_by_being),
                SqliteMigration(5, _init_memory_graph_v5_drop_legacy_memory_links),
            ],
        )
        conn.execute(
            """
            INSERT INTO semantic_memory_entries_by_being (
                entry_id, being_id_value, text, evidence_episode_ids_json,
                confidence, created_at, importance_score, tags_json, player_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-e1",
                "ada",
                "旧行のテキスト",
                "[]",
                0.5,
                datetime.now(timezone.utc).isoformat(),
                5,
                "[]",
                1,
            ),
        )
        conn.commit()

        # ここでマイグレーション v6 が走る (belief journal カラム追加)。
        store = SqliteSemanticMemoryStore(conn)
        loaded = store.list_for_being(BeingId("ada"))
        assert len(loaded) == 1
        entry = loaded[0]
        assert entry.entry_id == "legacy-e1"
        # belief_id は空文字→ entry_id にフォールバックする。
        assert entry.belief_id == "legacy-e1"
        assert entry.status == "active"
        assert entry.supersedes is None
        assert entry.support_evidence_ids == ()
        assert entry.contradict_evidence_ids == ()
