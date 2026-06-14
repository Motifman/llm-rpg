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


class TestScenarioMetadata:
    """Phase 7: scenario メタデータの埋め込み + cross-scenario transfer 検知。"""

    def test_capture_は_source_scenario_を_metadata_に書き込む(
        self, tmp_path: Path
    ) -> None:
        from ai_rpg_world.application.being.being_snapshot_file_gateway import (
            BeingSnapshotFileGateway,
        )

        wiring, prov = _make_wiring_stub()
        prov.ensure_attached(PlayerId(1))
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        session.capture_all(
            [PlayerId(1)], source_scenario="decay_demo"
        )

        gateway = BeingSnapshotFileGateway()
        files = list((tmp_path / "snap").iterdir())
        assert len(files) == 1
        metadata = gateway.read_metadata(files[0])
        assert metadata is not None
        assert metadata.source_scenario == "decay_demo"
        assert metadata.captured_at is not None  # ISO 8601 文字列

    def test_同じ_scenario_の_restore_は_cross_transfer_に乗らない(
        self, tmp_path: Path
    ) -> None:
        src_wiring, src_prov = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        src_session = ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "snap"
        )
        src_session.capture_all([PlayerId(1)], source_scenario="A")

        dst_wiring, _ = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap"
        )
        report = dst_session.restore_all_from_dir(
            tmp_path / "snap", current_scenario="A"
        )
        assert report.cross_scenario_transfers == []
        assert len(report.metadata_by_being) == 1

    def test_別_scenario_への_restore_は_warning_と_report_に乗る(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """同じ Being を別シナリオに転送する use case が許容されることを担保。"""
        src_wiring, src_prov = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        src_session = ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "snap"
        )
        src_session.capture_all([PlayerId(1)], source_scenario="forest_world")

        dst_wiring, _ = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap"
        )
        with caplog.at_level("WARNING"):
            report = dst_session.restore_all_from_dir(
                tmp_path / "snap", current_scenario="desert_world"
            )
        # restore 自体は成功
        assert len(report.restored) == 1
        # cross-transfer に記録される
        assert len(report.cross_scenario_transfers) == 1
        bid, src, cur = report.cross_scenario_transfers[0]
        assert src == "forest_world"
        assert cur == "desert_world"
        # warning ログにも出る
        assert any(
            "cross-scenario transfer" in r.message for r in caplog.records
        )

    def test_旧_snapshot_dir_に_world_json_が無い_restore_は_world_skip(
        self, tmp_path: Path
    ) -> None:
        """Phase 9-1: world.json なしの snapshot dir (= Phase 6 までの形式) の
        後方互換。restore_world_from_dir が None を返す。"""
        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        empty = tmp_path / "no_world"
        empty.mkdir()
        result = session.restore_world_from_dir(
            runtime=None, input_dir=empty, current_scenario="demo"
        )
        assert result is None

    def test_capture_world_で_world_json_が出る(self, tmp_path: Path) -> None:
        """Phase 9-2: 既定 subsystem codec が登録されたので、capture_world
        には runtime が必要。空の subsystem 群でも世界 snapshot が成立する
        ことを担保するため、minimum stub を渡す。"""
        from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
            InMemoryGameTimeProvider,
        )

        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        # codec が必要とする最小限の attribute を持つ stub。
        stub_runtime = SimpleNamespace(
            _time_provider=InMemoryGameTimeProvider(initial_tick=42),
            _spot_graph_repo=None,
            _player_status_repo=None,
            get_player_ids=lambda: [],
            get_player_spot_id=lambda pid: None,
        )
        # _spot_graph_repo=None だと position codec が raise する。
        # codec を override したいので、subsystem codec を入れない session を
        # 別建てで作る (= 配線確認のみが目的)。
        from ai_rpg_world.application.being.world_state_snapshot_service import (
            WorldStateSnapshotService,
        )

        session._world_snapshot_service = WorldStateSnapshotService()
        path = session.capture_world(
            runtime=stub_runtime, source_scenario="demo", world_tick=42
        )
        assert path.exists()
        assert path.name == "world.json"

    def test_world_snapshot_の_scenario_mismatch_は_fail_fast(
        self, tmp_path: Path
    ) -> None:
        """Phase 9-1: world は scenario 不一致を hard-error で弾く。"""
        from ai_rpg_world.application.being.world_state_snapshot import (
            WorldStateScenarioMismatchError,
        )
        from ai_rpg_world.application.being.world_state_snapshot_service import (
            WorldStateSnapshotService,
        )

        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        # 既定 codec を空にして配線テストのみ
        session._world_snapshot_service = WorldStateSnapshotService()
        # forest_world で save
        session.capture_world(
            runtime=SimpleNamespace(), source_scenario="forest_world", world_tick=10
        )
        # desert_world で load → fail-fast
        with pytest.raises(WorldStateScenarioMismatchError, match="forest_world"):
            session.restore_world_from_dir(
                runtime=SimpleNamespace(),
                input_dir=tmp_path / "snap",
                current_scenario="desert_world",
            )

    def test_metadata_なし_旧_snapshot_の_restore_は_問題なく動く(
        self, tmp_path: Path
    ) -> None:
        """``_metadata`` キー無しの旧 snapshot ファイルでも壊れない (後方互換)。"""
        from ai_rpg_world.application.being.being_snapshot_file_gateway import (
            BeingSnapshotFileGateway,
        )
        from ai_rpg_world.domain.being.value_object.being_snapshot import (
            BeingSnapshot,
        )

        snap_dir = tmp_path / "old"
        snap_dir.mkdir()
        # metadata=None で write = ``_metadata`` キーが書かれない
        gateway = BeingSnapshotFileGateway()
        snap = BeingSnapshot(
            being_id_value="being_w1_p1",
            identity_name="agent",
            identity_first_person="わたし",
            attachment_world_id=1,
            attachment_player_id=1,
            declared_memory_kinds=(),
            snapshot_version=2,
            memory_payload_json=None,
        )
        gateway.write(snap, snap_dir / "being_w1_p1.json")  # metadata 省略

        wiring, _ = _make_wiring_stub()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        report = session.restore_all_from_dir(
            snap_dir, current_scenario="anything"
        )
        assert len(report.restored) == 1
        assert report.cross_scenario_transfers == []  # 比較対象がないので空
        # metadata_by_being には None が入る
        assert all(v is None for v in report.metadata_by_being.values())
