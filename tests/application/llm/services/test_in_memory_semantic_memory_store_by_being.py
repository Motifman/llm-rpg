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

    def test_being_id_keyed_で_entry_を追加できる(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """add → list_for_being で取り出せる。"""
        being_id = BeingId("ada")
        entry = _make_entry()
        store.add_by_being(being_id, entry)
        result = store.list_for_being(being_id)
        assert result == [entry]

    def test_同一_entry_id_は_upsert_される(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """既存 entry_id を再度 add すると上書きされる (= 件数増えない)。"""
        being_id = BeingId("ada")
        store.add_by_being(being_id, _make_entry(text="v1"))
        store.add_by_being(being_id, _make_entry(text="v2"))
        result = store.list_for_being(being_id)
        assert len(result) == 1
        assert result[0].text == "v2"

    def test_異なる_being_id_の_entry_は混ざらない(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """ada と ben で同じ entry_id でも独立して保持される。"""
        store.add_by_being(BeingId("ada"), _make_entry(entry_id="e1", text="ada-side"))
        store.add_by_being(BeingId("ben"), _make_entry(entry_id="e1", text="ben-side"))
        assert store.list_for_being(BeingId("ada"))[0].text == "ada-side"
        assert store.list_for_being(BeingId("ben"))[0].text == "ben-side"

    def test_型違反は_TypeError(self, store: InMemorySemanticMemoryStore) -> None:
        """being_id / entry の型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.add_by_being("ada", _make_entry())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="entry"):
            store.add_by_being(BeingId("ada"), "not-an-entry")  # type: ignore[arg-type]


class TestListForBeing:
    """list_for_being の挙動。"""

    def test_未登録_being_には空リスト(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """未登録 being_id は空リスト。"""
        assert store.list_for_being(BeingId("nobody")) == []

    def test_created_at_降順で返る(
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

    def test_初回は_True_既存は_False(
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

    def test_異なる_being_id_なら独立して登録(
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

    def test_型違反は_TypeError(self, store: InMemorySemanticMemoryStore) -> None:
        """being_id / signature の型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.register_cluster_signature_if_new_by_being(
                "ada", "sig"  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="evidence_signature"):
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), 123  # type: ignore[arg-type]
            )


class TestIndependenceFromPlayerIdApi:
    """新旧 API の独立性 (= 並走 store は同期しない)。"""

    def test_player_id_経由で追加した_entry_は_being_id_経由では見えない(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """旧 API で追加すると新 API からは取れない (独立 namespace)。"""
        store.add(_make_entry(player_id=2))
        assert store.list_for_being(BeingId("ada")) == []

    def test_being_id_経由で追加した_entry_は_player_id_経由では見えない(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """逆方向も独立。"""
        store.add_by_being(BeingId("ada"), _make_entry(player_id=2))
        assert store.list_for_player(2) == []

    def test_cluster_signature_も独立(
        self, store: InMemorySemanticMemoryStore
    ) -> None:
        """signature 集合も新旧で混ざらない。"""
        store.register_cluster_signature_if_new(2, "sig-a")
        # 同 signature を being 側で登録しても初回扱い
        assert (
            store.register_cluster_signature_if_new_by_being(
                BeingId("ada"), "sig-a"
            )
            is True
        )
