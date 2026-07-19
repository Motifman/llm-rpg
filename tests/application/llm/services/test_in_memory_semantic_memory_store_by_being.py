"""InMemorySemanticMemoryStore の being_id 版 API 挙動 (Phase 3 Step 3b-1)。

旧 ``player_id`` 版とは独立した namespace で動くこと、CRUD・cluster signature・
独立性を担保する。memo の Step 3a-1 と同じパターン。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
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
    )


@pytest.fixture
def store() -> InMemorySemanticMemoryStore:
    return InMemorySemanticMemoryStore()


class TestAddByBeing:
    """add_by_being の挙動。"""

    def test_being_id_keyed_entry(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """add → list_for_being で取り出せる。"""
        being_id = BeingId("ada")
        entry = _make_entry()
        store.add_by_being(being_id, entry)
        result = store.list_for_being(being_id)
        assert result == [entry]

    def test_same_entry_id_upsert(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """既存 entry_id を再度 add すると上書きされる (= 件数増えない)。"""
        being_id = BeingId("ada")
        store.add_by_being(being_id, _make_entry(text="v1"))
        store.add_by_being(being_id, _make_entry(text="v2"))
        result = store.list_for_being(being_id)
        assert len(result) == 1
        assert result[0].text == "v2"

    def test_being_id_entry(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """ada と ben で同じ entry_id でも独立して保持される。"""
        store.add_by_being(BeingId("ada"), _make_entry(entry_id="e1", text="ada-side"))
        store.add_by_being(BeingId("ben"), _make_entry(entry_id="e1", text="ben-side"))
        assert store.list_for_being(BeingId("ada"))[0].text == "ada-side"
        assert store.list_for_being(BeingId("ben"))[0].text == "ben-side"

    def test_value_raises_type_error_3(self, store: InMemorySemanticMemoryStore) -> None:
        """being_id / entry の型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.add_by_being("ada", _make_entry())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="entry"):
            store.add_by_being(BeingId("ada"), "not-an-entry")  # type: ignore[arg-type]


class TestListForBeing:
    """list_for_being の挙動。"""

    def test_unregistered_being_empty_list(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """未登録 being_id は空リスト。"""
        assert store.list_for_being(BeingId("nobody")) == []

    def test_returns_created(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """SQLite 実装と挙動を揃えるため、新しい順で返る。"""
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


class TestRegisterClusterSignatureByBeing:
    """register_cluster_signature_if_new_by_being の挙動。"""

    def test_first_true_existing_false(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """同一 (being, signature) ペアの 2 回目は False。"""
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

    def test_being_id_independently(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """同じ signature でも being_id が違えば独立。"""
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

    def test_value_raises_type_error_2(self, store: InMemorySemanticMemoryStore) -> None:
        """being_id / signature の型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.register_cluster_signature_if_new_by_being(
                "ada", "sig"  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="evidence_signature"):
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), 123  # type: ignore[arg-type]
            )


class TestListClusterSignaturesByBeing:
    """list_cluster_signatures_by_being の挙動 (Phase 4 Step 4-2a)。"""

    def test_returns_signature_dict(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """登録済 signature を辞書順で返す。"""
        b = BeingId("ada")
        store.register_cluster_signature_if_new_by_being(b, "z-sig")
        store.register_cluster_signature_if_new_by_being(b, "a-sig")
        assert store.list_cluster_signatures_by_being(b) == ["a-sig", "z-sig"]

    def test_other_being_signature(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """他 being の signature は混ざらない。"""
        store.register_cluster_signature_if_new_by_being(BeingId("ada"), "x")
        store.register_cluster_signature_if_new_by_being(BeingId("ben"), "y")
        assert store.list_cluster_signatures_by_being(BeingId("ada")) == ["x"]


class TestReplaceAllByBeing:
    """replace_all_by_being の挙動 (snapshot restore primitive)。"""

    def test_replace_all_replaces_entries_and_signatures(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """entries と signatures を一括置換できる。"""
        b = BeingId("ada")
        store.add_by_being(b, _make_entry("old"))
        store.register_cluster_signature_if_new_by_being(b, "old-sig")
        new = _make_entry("new")
        store.replace_all_by_being(b, [new], ["new-sig"])
        assert [e.entry_id for e in store.list_for_being(b)] == ["new"]
        assert store.list_cluster_signatures_by_being(b) == ["new-sig"]

    def test_empty_replacement_clears_entries_and_signatures(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """空入力で全クリアできる。"""
        b = BeingId("ada")
        store.add_by_being(b, _make_entry())
        store.register_cluster_signature_if_new_by_being(b, "sig")
        store.replace_all_by_being(b, [], [])
        assert store.list_for_being(b) == []
        assert store.list_cluster_signatures_by_being(b) == []

    def test_other_being_state_not_affected(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """他 being の状態は影響を受けない。"""
        store.add_by_being(BeingId("ada"), _make_entry("a1"))
        store.register_cluster_signature_if_new_by_being(BeingId("ada"), "sig-a")
        store.add_by_being(BeingId("ben"), _make_entry("b1"))
        store.register_cluster_signature_if_new_by_being(BeingId("ben"), "sig-b")
        store.replace_all_by_being(BeingId("ada"), [], [])
        assert [e.entry_id for e in store.list_for_being(BeingId("ben"))] == ["b1"]
        assert store.list_cluster_signatures_by_being(BeingId("ben")) == ["sig-b"]


# Phase 3 Step 3b-3 (Issue #470): legacy player_id 版 API が撤去されたため、
# 旧/新 API の独立性を検証していたテストクラス
# ``TestIndependenceFromPlayerIdApi`` は削除された。新 API のみが残り、
# being_id を一次キーとして扱う設計に統一されている。


class TestSupersedeByBeing:
    """supersede_by_being の挙動 (U3a: belief journal の revise 操作)。"""

    def test_old_superseded_new_active(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """old が superseded に new が active で追加される。"""
        b = BeingId("ada")
        old = _make_entry("old", text="拠点に資源はない")
        store.add_by_being(b, old)
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
        store.supersede_by_being(b, old_entry_id="old", new_entry=new)

        entries = {e.entry_id: e for e in store.list_for_being(b)}
        assert entries["old"].status == "superseded"
        assert entries["new"].status == "active"
        assert entries["new"].supersedes == "old"
        assert entries["new"].belief_id == old.belief_id

    def test_old_entry_id_new_entry(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """old entry id が存在しなくても new entry は追加される。"""
        b = BeingId("ada")
        new = _make_entry("new")
        store.supersede_by_being(b, old_entry_id="does-not-exist", new_entry=new)
        assert [e.entry_id for e in store.list_for_being(b)] == ["new"]

    def test_value_raises_type_error(self, store: InMemorySemanticMemoryStore) -> None:
        """型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.supersede_by_being(
                "ada", old_entry_id="old", new_entry=_make_entry()  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="new_entry"):
            store.supersede_by_being(
                BeingId("ada"), old_entry_id="old", new_entry="not-an-entry"  # type: ignore[arg-type]
            )


class TestUpdateStatusByBeing:
    """update_status_by_being の挙動 (U3a: 反証による inactive 化等)。"""

    def test_entry_status_updated(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """指定 entry の status が更新される。"""
        b = BeingId("ada")
        store.add_by_being(b, _make_entry("e1"))
        store.update_status_by_being(b, "e1", "inactive")
        assert store.list_for_being(b)[0].status == "inactive"

    def test_entry_id(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """存在しない entry id は無視される。"""
        b = BeingId("ada")
        store.add_by_being(b, _make_entry("e1"))
        store.update_status_by_being(b, "does-not-exist", "inactive")
        assert store.list_for_being(b)[0].status == "active"

    def test_other_entry_not_affected(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """他 entry は影響を受けない。"""
        b = BeingId("ada")
        store.add_by_being(b, _make_entry("e1"))
        store.add_by_being(b, _make_entry("e2"))
        store.update_status_by_being(b, "e1", "inactive")
        entries = {e.entry_id: e.status for e in store.list_for_being(b)}
        assert entries == {"e1": "inactive", "e2": "active"}


class TestInMemorySemanticFullFieldRoundtripContract:
    """全フィールドに非 default 値を入れた entry が add → list で完全一致して戻る契約テスト。

    SQLite 実装 (``TestSqliteSemanticFullFieldRoundtripContract``) と対をなす。
    in-memory は codec を持たず参照をそのまま保持するので現状は自明に通るが、
    「保存経路が entry を欠損させない」という store interface の契約を SQLite と
    同じ形で固定し、実装差を出さないための守り。
    """

    def _full_entry(self) -> SemanticMemoryEntry:
        return SemanticMemoryEntry(
            entry_id="e-full",
            player_id=7,
            text="全フィールドを非 default 値で埋めた belief",
            evidence_episode_ids=("ep-1", "ep-2"),
            confidence=0.42,
            created_at=datetime(2026, 7, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
            importance_score=9,
            tags=("t1", "t2"),
            belief_id="belief-x",
            status="superseded",
            supersedes="e-old",
            support_evidence_ids=("s1", "s2", "s3", "s4"),
            contradict_evidence_ids=("c1",),
            confirmation_support_count=2,
            hearsay_support_count=1,
        )

    def test_add_list_all_round_trips_exactly(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """add_by_being → list_for_being の往復で entry が元と完全一致する。"""
        being_id = BeingId("ada")
        entry = self._full_entry()
        store.add_by_being(being_id, entry)
        assert store.list_for_being(being_id)[0] == entry

    def test_replace_all_being_all_round_trips_exactly(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """replace_all_by_being → list_for_being の往復で entry が元と完全一致する。"""
        being_id = BeingId("ada")
        entry = self._full_entry()
        store.replace_all_by_being(being_id, [entry], [])
        assert store.list_for_being(being_id)[0] == entry
