"""ExperimentSnapshotSession の挙動 (Phase 6)。

実 ``LlmAgentWiringResult`` の代わりに minimum stub を組んで、capture_all /
restore_all_from_dir の集計動作を担保する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.being.experiment_snapshot_session import (
    ExperimentSnapshotSession,
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
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import (
    DEFAULT_SINGLE_WORLD_ID,
)
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


def _make_wiring_stub() -> tuple[SimpleNamespace, BeingProvisioningService]:
    """wiring 結果風の SimpleNamespace を作る。

    全 store は in-memory で揃え、Being の attach は呼出側 (テスト) が
    BeingProvisioningService 経由で行う。
    """
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    wiring = SimpleNamespace(
        memo_store=InMemoryMemoStore(),
        semantic_memory_store=InMemorySemanticMemoryStore(),
        memory_link_store=InMemoryMemoryLinkStore(),
        episodic_recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
        episodic_reinterpretation_journal_store=InMemoryEpisodicReinterpretationJournalStore(),
        episodic_episode_store=InMemorySubjectiveEpisodeStore(),
        being_repository=repo,
        being_attachment_resolver=resolver,
    )
    return wiring, provisioning


class TestConstructorGuards:
    """必須 / 任意 store の判定。"""

    def test_being_repository_missing_は_RuntimeError(self, tmp_path: Path) -> None:
        wiring, _ = _make_wiring_stub()
        wiring.being_repository = None
        with pytest.raises(RuntimeError, match="being_repository"):
            ExperimentSnapshotSession(
                wiring_result=wiring,
                snapshot_dir=tmp_path / "snap",
            )

    def test_memo_store_missing_は_空fallbackで動く(self, tmp_path: Path) -> None:
        """memo_store が None でも構築は成功し、capture は空 memo の snapshot を出す。"""
        from ai_rpg_world.application.being.being_provisioning_service import (
            BeingProvisioningService,
        )

        wiring, _ = _make_wiring_stub()
        # 改めて being_repository を直接保持、provisioning を別建てで作る。
        wiring.memo_store = None  # fallback 経路
        prov = BeingProvisioningService(wiring.being_repository)
        prov.ensure_attached(PlayerId(1))

        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        report = session.capture_all([PlayerId(1)])
        assert report.is_clean


class TestCaptureAll:
    """capture_all の集計動作。"""

    def test_2_player_全員_capture_できる(self, tmp_path: Path) -> None:
        wiring, provisioning = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        provisioning.ensure_attached(PlayerId(2))
        # memo にデータを入れて payload が空でないようにする。
        being_1 = wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(1)
        )
        assert being_1 is not None
        wiring.memo_store.add_by_being(being_1, "P1 memo")

        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        report = session.capture_all([PlayerId(1), PlayerId(2)])
        assert report.is_clean
        assert len(report.succeeded) == 2
        # 2 ファイル出力されている。
        files = sorted((tmp_path / "snap").iterdir())
        assert len(files) == 2
        assert all(f.suffix == ".json" for f in files)

    def test_attach_されていない_player_はスキップして警告(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        wiring, provisioning = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        # PlayerId(2) は attach されていない
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        with caplog.at_level("WARNING"):
            report = session.capture_all([PlayerId(1), PlayerId(2)])
        assert len(report.succeeded) == 1
        # warning ログに player_id=2 が出ている。
        assert any("player_id=2" in r.message for r in caplog.records)

    def test_1_player_の_capture_失敗は他の_player_を止めない(
        self, tmp_path: Path
    ) -> None:
        """memo_store の add_by_being が 1 being だけで例外を投げるよう細工し、
        他 player の capture は続行されることを担保する。"""
        wiring, provisioning = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        provisioning.ensure_attached(PlayerId(2))

        being_2 = wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(2)
        )
        assert being_2 is not None

        # memo_store の list_all_by_being を being_2 の時だけ raise させる。
        original = wiring.memo_store.list_all_by_being

        def _raising(being_id):
            if being_id == being_2:
                raise RuntimeError("synthetic failure")
            return original(being_id)

        wiring.memo_store.list_all_by_being = _raising  # type: ignore[assignment]

        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        report = session.capture_all([PlayerId(1), PlayerId(2)])
        # P1 は成功、P2 は failed に乗る。全体が止まらない。
        assert len(report.succeeded) == 1
        assert len(report.failed) == 1
        assert report.failed[0][0] == being_2
        # P1 の snapshot だけが書かれる。
        files = list((tmp_path / "snap").iterdir())
        assert len(files) == 1


class TestRestoreAll:
    """restore_all_from_dir の挙動。"""

    def test_capture_して_restore_で_memory_が一致する(self, tmp_path: Path) -> None:
        src_wiring, src_prov = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        being_1 = src_wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(1)
        )
        assert being_1 is not None
        src_wiring.memo_store.add_by_being(being_1, "from-source")
        src_session = ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "snap"
        )
        src_session.capture_all([PlayerId(1)])

        # dst で restore
        dst_wiring, _ = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap"
        )
        report = dst_session.restore_all_from_dir(tmp_path / "snap")
        assert len(report.restored) == 1
        memos = dst_wiring.memo_store.list_all_by_being(being_1)
        assert [m.content for m in memos] == ["from-source"]

    def test_存在しない_ディレクトリは_FileNotFoundError(self, tmp_path: Path) -> None:
        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        with pytest.raises(FileNotFoundError):
            session.restore_all_from_dir(tmp_path / "no-such-dir")

    def test_空ディレクトリは_no_op(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        report = session.restore_all_from_dir(empty)
        assert report.restored == []

    def test_壊れた_JSON_は例外で全体停止(self, tmp_path: Path) -> None:
        wiring, _ = _make_wiring_stub()
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "broken.json").write_text("not json", encoding="utf-8")
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        with pytest.raises(Exception):
            session.restore_all_from_dir(bad_dir)
