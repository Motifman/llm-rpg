"""BeingPersistenceService の save / load round-trip 挙動 (Phase 4 Step 4-3)。

5 memory store + Being aggregate を 1 単位で save / load できることを担保する。
in-memory + sqlite 両環境で full round-trip テスト。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_persistence_service import (
    BeingPersistenceService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
    SqliteBeingRepository,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _build_persistence_service(
    being_repo,
) -> tuple[BeingPersistenceService, dict[str, object]]:
    from ai_rpg_world.application.llm.services.afterglow_store import (
        InMemoryAfterglowStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        InMemoryEpisodicRecallHabituationStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        InMemoryEpisodicRecallSlotStore,
    )

    memo = InMemoryMemoStore()
    semantic = InMemorySemanticMemoryStore()
    link = InMemoryMemoryLinkStore()
    recall = InMemoryEpisodicRecallBufferStore()
    journal = InMemoryEpisodicReinterpretationJournalStore()
    episode = InMemorySubjectiveEpisodeStore()
    snapshot_svc = BeingMemorySnapshotService(
        memo_store=memo,
        semantic_store=semantic,
        memory_link_store=link,
        recall_buffer_store=recall,
        reinterpretation_journal_store=journal,
        episodic_episode_store=episode,
        recall_slot_store=InMemoryEpisodicRecallSlotStore(),
        afterglow_store=InMemoryAfterglowStore(),
        recall_habituation_store=InMemoryEpisodicRecallHabituationStore(),
    )
    svc = BeingPersistenceService(
        being_repository=being_repo,
        memory_snapshot_service=snapshot_svc,
    )
    return svc, {
        "memo": memo,
        "semantic": semantic,
        "link": link,
        "recall": recall,
        "journal": journal,
        "episode": episode,
    }


def _make_being(being_id_value: str = "being_w1_p1") -> Being:
    return Being(
        being_id=BeingId(being_id_value),
        identity=BeingIdentity(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(world_id=WorldId(1), player_id=PlayerId(1)),
        declared_memory_kinds=[MemoryKind.MEMO, MemoryKind.SEMANTIC],
    )


def _populate_memory(stores: dict[str, object], being: BeingId) -> None:
    stores["memo"].add_by_being(being, "Adventure memo")
    stores["semantic"].add_by_being(
        being,
        SemanticMemoryEntry(
            entry_id="s1",
            player_id=1,
            text="森は東にある",
            evidence_episode_ids=("ep-1",),
            confidence=0.7,
            created_at=_NOW,
        ),
    )


class TestSaveLoadRoundTripInMemory:
    """InMemoryBeingRepository での save → load round-trip。"""

    def test_save_すると_payload_付き_v2_snapshot_が保存される(self) -> None:
        repo = InMemoryBeingRepository()
        svc, stores = _build_persistence_service(repo)
        being = _make_being()
        _populate_memory(stores, being.being_id)
        svc.save(being)
        snap = repo.find_snapshot_by_id(being.being_id)
        assert snap is not None
        assert snap.has_memory_payload is True
        assert snap.snapshot_version == 2

    def test_save_load_で_memory_状態が一致する(self) -> None:
        # source 環境にデータを詰めて save。
        src_repo = InMemoryBeingRepository()
        src_svc, src_stores = _build_persistence_service(src_repo)
        being = _make_being()
        _populate_memory(src_stores, being.being_id)
        src_svc.save(being)

        # snapshot を別 repo にコピーして dst 環境を構築 (= 別マシン想定)。
        snap = src_repo.find_snapshot_by_id(being.being_id)
        assert snap is not None
        dst_repo = InMemoryBeingRepository()
        dst_repo.save_snapshot(snap)
        dst_svc, dst_stores = _build_persistence_service(dst_repo)

        loaded = dst_svc.load(being.being_id)
        assert loaded is not None
        assert loaded.being_id == being.being_id
        # memory が dst の store に復元されている。
        assert len(dst_stores["memo"].list_all_by_being(being.being_id)) == 1
        assert len(dst_stores["semantic"].list_for_being(being.being_id)) == 1

    def test_未登録_being_id_は_None(self) -> None:
        repo = InMemoryBeingRepository()
        svc, _ = _build_persistence_service(repo)
        assert svc.load(BeingId("missing")) is None

    def test_payload_なし_snapshot_の_load_は_memory_restore_を呼ばない(
        self,
    ) -> None:
        """``BeingRepository.save(being)`` 経由で保存された v2 (payload=None) snapshot は
        load 時に memory restore がスキップされる。"""
        repo = InMemoryBeingRepository()
        svc, stores = _build_persistence_service(repo)
        being = _make_being()
        # payload なしで save (= 旧 API 経路)
        repo.save(being)
        # dst 側 memory store には先に別データを入れておく。
        stores["memo"].add_by_being(being.being_id, "should-survive")
        loaded = svc.load(being.being_id)
        assert loaded is not None
        # memory restore が呼ばれていないので既存データはそのまま。
        contents = [
            e.content for e in stores["memo"].list_all_by_being(being.being_id)
        ]
        assert "should-survive" in contents


class TestSaveLoadRoundTripSqlite:
    """SqliteBeingRepository でも同じ round-trip が成立すること。"""

    def test_sqlite_save_load_で_memory_が_復元される(self) -> None:
        src_conn = sqlite3.connect(":memory:", check_same_thread=False)
        src_repo = SqliteBeingRepository(src_conn)
        src_svc, src_stores = _build_persistence_service(src_repo)
        being = _make_being()
        _populate_memory(src_stores, being.being_id)
        src_svc.save(being)

        # 別 sqlite ファイル / 接続を装う: snapshot を取り出して別 repo に渡す。
        snap = src_repo.find_snapshot_by_id(being.being_id)
        assert snap is not None and snap.has_memory_payload

        dst_conn = sqlite3.connect(":memory:", check_same_thread=False)
        dst_repo = SqliteBeingRepository(dst_conn)
        dst_repo.save_snapshot(snap)
        dst_svc, dst_stores = _build_persistence_service(dst_repo)

        loaded = dst_svc.load(being.being_id)
        assert loaded is not None
        memos = dst_stores["memo"].list_all_by_being(being.being_id)
        assert [m.content for m in memos] == ["Adventure memo"]


class TestConstructorTypeGuards:
    def test_being_repository_型違反(self) -> None:
        from ai_rpg_world.application.llm.services.afterglow_store import (
            InMemoryAfterglowStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            InMemoryEpisodicRecallSlotStore,
        )

        memo = InMemoryMemoStore()
        semantic = InMemorySemanticMemoryStore()
        link = InMemoryMemoryLinkStore()
        recall = InMemoryEpisodicRecallBufferStore()
        journal = InMemoryEpisodicReinterpretationJournalStore()
        episode = InMemorySubjectiveEpisodeStore()
        snap_svc = BeingMemorySnapshotService(
            memo_store=memo,
            semantic_store=semantic,
            memory_link_store=link,
            recall_buffer_store=recall,
            reinterpretation_journal_store=journal,
            episodic_episode_store=episode,
            recall_slot_store=InMemoryEpisodicRecallSlotStore(),
            afterglow_store=InMemoryAfterglowStore(),
            recall_habituation_store=InMemoryEpisodicRecallHabituationStore(),
        )
        with pytest.raises(TypeError, match="being_repository"):
            BeingPersistenceService(
                being_repository="bad",  # type: ignore[arg-type]
                memory_snapshot_service=snap_svc,
            )

    def test_memory_snapshot_service_型違反(self) -> None:
        with pytest.raises(TypeError, match="memory_snapshot_service"):
            BeingPersistenceService(
                being_repository=InMemoryBeingRepository(),
                memory_snapshot_service="bad",  # type: ignore[arg-type]
            )

    def test_save_の_being_型違反(self) -> None:
        repo = InMemoryBeingRepository()
        svc, _ = _build_persistence_service(repo)
        with pytest.raises(TypeError):
            svc.save("not-a-being")  # type: ignore[arg-type]

    def test_load_の_being_id_型違反(self) -> None:
        repo = InMemoryBeingRepository()
        svc, _ = _build_persistence_service(repo)
        with pytest.raises(TypeError):
            svc.load("ada")  # type: ignore[arg-type]
