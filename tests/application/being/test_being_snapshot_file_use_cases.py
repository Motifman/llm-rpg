"""capture / restore use case の round-trip 挙動 (Phase 5)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
)
from ai_rpg_world.application.being.capture_being_snapshot_to_file_use_case import (
    BeingNotFoundForSnapshotError,
    CaptureBeingSnapshotToFileUseCase,
)
from ai_rpg_world.application.being.restore_being_snapshot_from_file_use_case import (
    RestoreBeingSnapshotFromFileUseCase,
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


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _make_environment():
    """新規 store 群 + 2 use case + gateway を組んで返す。"""
    repo = InMemoryBeingRepository()
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
    memory_snapshot = BeingMemorySnapshotService(
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
    gateway = BeingSnapshotFileGateway()
    capture = CaptureBeingSnapshotToFileUseCase(
        being_repository=repo,
        memory_snapshot_service=memory_snapshot,
        file_gateway=gateway,
    )
    restore = RestoreBeingSnapshotFromFileUseCase(
        being_repository=repo,
        memory_snapshot_service=memory_snapshot,
        file_gateway=gateway,
    )
    return {
        "repo": repo,
        "memo": memo,
        "semantic": semantic,
        "link": link,
        "recall": recall,
        "journal": journal,
        "episode": episode,
        "capture": capture,
        "restore": restore,
    }


def _make_being() -> Being:
    return Being(
        being_id=BeingId("being_w1_p1"),
        identity=BeingIdentity(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(world_id=WorldId(1), player_id=PlayerId(1)),
        declared_memory_kinds=[MemoryKind.MEMO, MemoryKind.SEMANTIC],
    )


class TestCaptureUseCase:
    def test_未登録_being_は_例外(self, tmp_path: Path) -> None:
        env = _make_environment()
        with pytest.raises(BeingNotFoundForSnapshotError):
            env["capture"].execute(BeingId("missing"), tmp_path / "x.json")

    def test_capture_は_ファイルを書き出し_repo_を変更しない(
        self, tmp_path: Path
    ) -> None:
        env = _make_environment()
        being = _make_being()
        env["repo"].save(being)
        env["memo"].add_by_being(being.being_id, "memo 1")

        out = tmp_path / "snap.json"
        result = env["capture"].execute(being.being_id, out)

        assert out.exists()
        assert result.snapshot_version == 2
        assert result.has_memory_payload is True
        # repo の snapshot は capture 前と同じ (= memory なし v2)
        snap = env["repo"].find_snapshot_by_id(being.being_id)
        assert snap is not None
        assert snap.has_memory_payload is False


class TestRestoreUseCase:
    def test_capture_して_restore_すると_memory_が復元される(
        self, tmp_path: Path
    ) -> None:
        """source 側 → file → 別 dst 環境への完全 round-trip。"""
        src = _make_environment()
        being = _make_being()
        src["repo"].save(being)
        src["memo"].add_by_being(being.being_id, "Adventure")
        src["semantic"].add_by_being(
            being.being_id,
            SemanticMemoryEntry(
                entry_id="s1",
                player_id=1,
                text="森は東",
                evidence_episode_ids=("ep-1",),
                confidence=0.7,
                created_at=_NOW,
            ),
        )
        snap_path = tmp_path / "snap.json"
        src["capture"].execute(being.being_id, snap_path)

        dst = _make_environment()
        result = dst["restore"].execute(snap_path)
        assert result.memory_restored is True

        # dst 側の memory store にデータが復元されている。
        memos = dst["memo"].list_all_by_being(being.being_id)
        assert [m.content for m in memos] == ["Adventure"]
        sems = dst["semantic"].list_for_being(being.being_id)
        assert [e.entry_id for e in sems] == ["s1"]
        # dst の repo にも snapshot が登録される。
        loaded = dst["repo"].find_by_id(being.being_id)
        assert loaded is not None
        assert loaded.identity.name == "アダ"

    def test_payload_なし_snapshot_の_restore_は_memory_スキップ(
        self, tmp_path: Path
    ) -> None:
        """v1 snapshot 想定: memory_payload_json=None なら memory_restored=False。"""
        from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot

        env = _make_environment()
        snap = BeingSnapshot(
            being_id_value="being_w1_p1",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=1,
            attachment_player_id=1,
            declared_memory_kinds=("memo",),
            snapshot_version=2,
            memory_payload_json=None,
        )
        path = tmp_path / "v2-no-memory.json"
        BeingSnapshotFileGateway().write(snap, path)

        result = env["restore"].execute(path)
        assert result.memory_restored is False
        # repo には保存される。
        assert env["repo"].find_snapshot_by_id(BeingId("being_w1_p1")) is not None


class TestConstructorTypeGuards:
    def test_capture_constructor_型違反(self) -> None:
        with pytest.raises(TypeError, match="being_repository"):
            CaptureBeingSnapshotToFileUseCase(
                being_repository="bad",  # type: ignore[arg-type]
                memory_snapshot_service=_make_environment()["capture"]._memory,  # noqa: SLF001
                file_gateway=BeingSnapshotFileGateway(),
            )

    def test_restore_constructor_型違反(self) -> None:
        with pytest.raises(TypeError, match="file_gateway"):
            RestoreBeingSnapshotFromFileUseCase(
                being_repository=InMemoryBeingRepository(),
                memory_snapshot_service=_make_environment()["capture"]._memory,  # noqa: SLF001
                file_gateway="bad",  # type: ignore[arg-type]
            )

    def test_execute_の引数型違反(self, tmp_path: Path) -> None:
        env = _make_environment()
        with pytest.raises(TypeError):
            env["capture"].execute("ada", tmp_path / "x.json")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            env["capture"].execute(BeingId("x"), "string-not-path")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            env["restore"].execute("string-not-path")  # type: ignore[arg-type]
