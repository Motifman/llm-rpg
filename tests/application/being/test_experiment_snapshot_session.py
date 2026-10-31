"""ExperimentSnapshotSession の挙動 (Phase 6)。

実 ``LlmAgentWiringResult`` の代わりに minimum stub を組んで、capture_all /
restore_all_from_dir の集計動作を担保する。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.being_attachment_resolver import BeingAttachmentResolver
from ai_rpg_world.application.being.being_provisioning_service import BeingProvisioningService
from ai_rpg_world.application.being.being_snapshot_file_gateway import BeingSnapshotFileGateway
from ai_rpg_world.application.being.experiment_snapshot_session import (
    EXPECTED_WORLD_SUBSYSTEM_KEYS,
    ExperimentSnapshotSession,
    _default_world_subsystem_codecs,
)
from ai_rpg_world.being.domain.being_attachment import BeingAttachment as _BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import InMemoryShortTermMemoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository

_ENVIRONMENT = _BeingAttachment(environment_id="demo#1", environment_name="試験の世界")


def _make_wiring_stub() -> tuple[SimpleNamespace, BeingProvisioningService]:
    """wiring 結果風の SimpleNamespace を作る。

    全 store は in-memory で揃え、Being の attach は呼出側 (テスト) が
    BeingProvisioningService 経由で行う。
    """
    repo = InMemoryBeingRepository()
    player_beings = PlayerBeings(DEFAULT_SINGLE_WORLD_ID)
    resolver = BeingAttachmentResolver(repo, player_beings)
    provisioning = BeingProvisioningService(repo, player_beings, _ENVIRONMENT)
    wiring = SimpleNamespace(
        being_repository=repo,
        being_attachment_resolver=resolver,
        player_beings=player_beings,
        being_environment=_ENVIRONMENT,
        acquaintance_store=InMemoryAcquaintanceRepository(),
        being_episode_store=InMemoryEpisodeRepository(),
        being_memo_store=InMemoryMemoBookRepository(),
        memory_turn_clock=InMemoryMemoryTurnClock(),
        being_short_term_memory_store=InMemoryShortTermMemoryRepository(),
    )
    return (wiring, provisioning)


class TestConstructorGuards:
    """必須 / 任意 store の判定。"""

    def test_being_repository_missing_raises_runtime_error(self, tmp_path: Path) -> None:
        """being repository missing は RuntimeError。"""
        (wiring, _) = _make_wiring_stub()
        wiring.being_repository = None
        with pytest.raises(RuntimeError, match="being_repository"):
            ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")

    def test_being_episode_store_missing_raises_runtime_error(self, tmp_path: Path) -> None:
        """目次つきのエピソードの store が無い wiring では、空の store で代用せず RuntimeError で止まる。代用すると、再開した Being が書いた記憶を忘れたことと配線漏れが見分けられない。"""
        (wiring, _) = _make_wiring_stub()
        wiring.being_episode_store = None
        with pytest.raises(RuntimeError, match="being_episode_store"):
            ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")

    def test_being_memo_store_missing_raises_runtime_error(self, tmp_path: Path) -> None:
        """メモ帳の store が無い wiring では、空の store で代用せず RuntimeError で止まる。代用すると、再開した Being がメモを忘れたことと配線漏れが見分けられない。"""
        (wiring, _) = _make_wiring_stub()
        wiring.being_memo_store = None
        with pytest.raises(RuntimeError, match="being_memo_store"):
            ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")

    def test_memory_turn_clock_missing_raises_runtime_error(self, tmp_path: Path) -> None:
        """記憶のターン数の時計が無い wiring では、空の時計で代用せず RuntimeError で止まる。代用すると、再開した Being のターン数が 0 に戻り、記憶に付くターン数が前の回と重なる。"""
        (wiring, _) = _make_wiring_stub()
        wiring.memory_turn_clock = None
        with pytest.raises(RuntimeError, match="memory_turn_clock"):
            ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")


class TestWorldSubsystemCoverage:
    """world snapshot の既定 subsystem 一覧を構造で固定する。"""

    def test_default_world_subsystem_keys_match_expected_keys(self) -> None:
        """既定 codec の key が期待一覧と同じ順序・同じ集合で登録される。"""
        keys = [codec.subsystem_key for codec in _default_world_subsystem_codecs()]
        assert keys == list(EXPECTED_WORLD_SUBSYSTEM_KEYS)


class TestCaptureAll:
    """capture_all の集計動作。"""

    def test_two_player_all_players_capture(self, tmp_path: Path) -> None:
        """2 player 全員 capture できる。"""
        (wiring, provisioning) = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        provisioning.ensure_attached(PlayerId(2))
        being_1 = wiring.being_attachment_resolver.resolve_being_id(DEFAULT_SINGLE_WORLD_ID, PlayerId(1))
        assert being_1 is not None
        wiring.acquaintance_store.record_meeting(being_1, environment_name="島", name="カイト", turn=1)
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        report = session.capture_all([PlayerId(1), PlayerId(2)])
        assert report.is_clean
        assert len(report.succeeded) == 2
        files = sorted((tmp_path / "snap").iterdir())
        assert len(files) == 2
        assert all(f.suffix == ".json" for f in files)

    def test_emits_warning_for_attach_player(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """attach されていない player はスキップして警告。"""
        (wiring, provisioning) = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        with caplog.at_level("WARNING"):
            report = session.capture_all([PlayerId(1), PlayerId(2)])
        assert len(report.succeeded) == 1
        assert any("player_id=2" in r.message for r in caplog.records)

    def test_one_player_capture_failure_other_player_does_not_stop(self, tmp_path: Path) -> None:
        """知り合いの store の読み出しが 1 being だけで例外を投げるよう細工し、
        他 player の capture は続行されることを担保する。"""
        (wiring, provisioning) = _make_wiring_stub()
        provisioning.ensure_attached(PlayerId(1))
        provisioning.ensure_attached(PlayerId(2))
        being_2 = wiring.being_attachment_resolver.resolve_being_id(DEFAULT_SINGLE_WORLD_ID, PlayerId(2))
        assert being_2 is not None
        original = wiring.acquaintance_store.list_by_being

        def _raising(being_id):
            if being_id == being_2:
                raise RuntimeError("synthetic failure")
            return original(being_id)

        wiring.acquaintance_store.list_by_being = _raising
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        report = session.capture_all([PlayerId(1), PlayerId(2)])
        assert len(report.succeeded) == 1
        assert len(report.failed) == 1
        assert report.failed[0][0] == being_2
        files = list((tmp_path / "snap").iterdir())
        assert len(files) == 1


class TestRestoreAll:
    """restore_all_from_dir の挙動。"""

    def test_capture_restore_memory_matches(self, tmp_path: Path) -> None:
        """capture して restore で memory が一致する。"""
        (src_wiring, src_prov) = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        being_1 = src_wiring.being_attachment_resolver.resolve_being_id(DEFAULT_SINGLE_WORLD_ID, PlayerId(1))
        assert being_1 is not None
        src_wiring.acquaintance_store.record_meeting(being_1, environment_name="島", name="カイト", turn=1)
        src_session = ExperimentSnapshotSession(wiring_result=src_wiring, snapshot_dir=tmp_path / "snap")
        src_session.capture_all([PlayerId(1)])
        (dst_wiring, _) = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap")
        report = dst_session.restore_all_from_dir(tmp_path / "snap")
        assert len(report.restored) == 1
        assert [a.name for a in dst_wiring.acquaintance_store.list_by_being(being_1)] == ["カイト"]

    def test_report_lists_removed_memory_keys_only_for_beings_that_had_them(self, tmp_path: Path) -> None:
        """古いメモの欄を持つ snapshot だけが、Being ごとの捨てた件数として報告に載る。持たない Being は載らない。"""
        (src_wiring, src_prov) = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        src_prov.ensure_attached(PlayerId(2))
        being_1 = src_wiring.being_attachment_resolver.resolve_being_id(DEFAULT_SINGLE_WORLD_ID, PlayerId(1))
        assert being_1 is not None
        ExperimentSnapshotSession(wiring_result=src_wiring, snapshot_dir=tmp_path / "snap").capture_all(
            [PlayerId(1), PlayerId(2)]
        )
        gateway = BeingSnapshotFileGateway()
        old_path = tmp_path / "snap" / f"{being_1.value}.json"
        snapshot = gateway.read(old_path)
        payload = {
            **json.loads(snapshot.memory_payload_json),
            "memo": [{"id": "m1", "added_at_tick": 90}, {"id": "m2", "added_at_tick": 91}],
        }
        gateway.write(dataclasses.replace(snapshot, memory_payload_json=json.dumps(payload)), old_path)
        (dst_wiring, _) = _make_wiring_stub()

        report = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "dst"
        ).restore_all_from_dir(tmp_path / "snap")

        assert len(report.restored) == 2
        assert report.removed_memory_key_counts == {being_1: {"memo": 2}}

    def test_missing_raises_file_not_found_error(self, tmp_path: Path) -> None:
        """存在しない ディレクトリは FileNotFoundError。"""
        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        with pytest.raises(FileNotFoundError):
            session.restore_all_from_dir(tmp_path / "no-such-dir")

    def test_empty_directory_op(self, tmp_path: Path) -> None:
        """空ディレクトリは no op。"""
        empty = tmp_path / "empty"
        empty.mkdir()
        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        report = session.restore_all_from_dir(empty)
        assert report.restored == []

    def test_invalid_json_all_raises_exception(self, tmp_path: Path) -> None:
        """壊れた JSON は例外で全体停止。"""
        (wiring, _) = _make_wiring_stub()
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "broken.json").write_text("not json", encoding="utf-8")
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        with pytest.raises(Exception):
            session.restore_all_from_dir(bad_dir)


class TestScenarioMetadata:
    """Phase 7: scenario メタデータの埋め込み + cross-scenario transfer 検知。"""

    def test_writes_capture_source_scenario_metadata(self, tmp_path: Path) -> None:
        """capture は source scenario を metadata に書き込む。"""
        from ai_rpg_world.application.being.being_snapshot_file_gateway import BeingSnapshotFileGateway

        (wiring, prov) = _make_wiring_stub()
        prov.ensure_attached(PlayerId(1))
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        session.capture_all([PlayerId(1)], source_scenario="decay_demo")
        gateway = BeingSnapshotFileGateway()
        files = list((tmp_path / "snap").iterdir())
        assert len(files) == 1
        metadata = gateway.read_metadata(files[0])
        assert metadata is not None
        assert metadata.source_scenario == "decay_demo"
        assert metadata.captured_at is not None

    def test_same_scenario_restore_cross_transfer_not_included(self, tmp_path: Path) -> None:
        """同じ scenario の restore は cross transfer に乗らない。"""
        (src_wiring, src_prov) = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        src_session = ExperimentSnapshotSession(wiring_result=src_wiring, snapshot_dir=tmp_path / "snap")
        src_session.capture_all([PlayerId(1)], source_scenario="A")
        (dst_wiring, _) = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap")
        report = dst_session.restore_all_from_dir(tmp_path / "snap", current_scenario="A")
        assert report.cross_scenario_transfers == []
        assert len(report.metadata_by_being) == 1

    def test_emits_warning_for_different_scenario_restore_re_port(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """同じ Being を別シナリオに転送する use case が許容されることを担保。"""
        (src_wiring, src_prov) = _make_wiring_stub()
        src_prov.ensure_attached(PlayerId(1))
        src_session = ExperimentSnapshotSession(wiring_result=src_wiring, snapshot_dir=tmp_path / "snap")
        src_session.capture_all([PlayerId(1)], source_scenario="forest_world")
        (dst_wiring, _) = _make_wiring_stub()
        dst_session = ExperimentSnapshotSession(wiring_result=dst_wiring, snapshot_dir=tmp_path / "snap")
        with caplog.at_level("WARNING"):
            report = dst_session.restore_all_from_dir(tmp_path / "snap", current_scenario="desert_world")
        assert len(report.restored) == 1
        assert len(report.cross_scenario_transfers) == 1
        (bid, src, cur) = report.cross_scenario_transfers[0]
        assert src == "forest_world"
        assert cur == "desert_world"
        assert any("cross-scenario transfer" in r.message for r in caplog.records)

    def test_legacy_snapshot_dir_world_json_restore_world_skip(self, tmp_path: Path) -> None:
        """Phase 9-1: world.json なしの snapshot dir (= Phase 6 までの形式) の
        後方互換。restore_world_from_dir が None を返す。"""
        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        empty = tmp_path / "no_world"
        empty.mkdir()
        result = session.restore_world_from_dir(runtime=None, input_dir=empty, current_scenario="demo")
        assert result is None

    def test_capture_world_json_rendered(self, tmp_path: Path) -> None:
        """Phase 9-2: 既定 subsystem codec が登録されたので、capture_world
        には runtime が必要。空の subsystem 群でも世界 snapshot が成立する
        ことを担保するため、minimum stub を渡す。"""
        from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider

        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        stub_runtime = SimpleNamespace(
            _time_provider=InMemoryGameTimeProvider(initial_tick=42),
            _spot_graph_repo=None,
            _player_status_repo=None,
            get_player_ids=lambda: [],
            get_player_spot_id=lambda pid: None,
        )
        from ai_rpg_world.application.being.world_state_snapshot_service import WorldStateSnapshotService

        session._world_snapshot_service = WorldStateSnapshotService()
        path = session.capture_world(runtime=stub_runtime, source_scenario="demo", world_tick=42)
        assert path.exists()
        assert path.name == "world.json"

    def test_world_snapshot_scenario_mismatch_fail_fast(self, tmp_path: Path) -> None:
        """Phase 9-1: world は scenario 不一致を hard-error で弾く。"""
        from ai_rpg_world.application.being.world_state_snapshot import WorldStateScenarioMismatchError
        from ai_rpg_world.application.being.world_state_snapshot_service import WorldStateSnapshotService

        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        session._world_snapshot_service = WorldStateSnapshotService()
        session.capture_world(runtime=SimpleNamespace(), source_scenario="forest_world", world_tick=10)
        with pytest.raises(WorldStateScenarioMismatchError, match="forest_world"):
            session.restore_world_from_dir(
                runtime=SimpleNamespace(), input_dir=tmp_path / "snap", current_scenario="desert_world"
            )

    def test_world_snapshot_restore_strict_missing_subsystem_fail_fast(self, tmp_path: Path) -> None:
        """実験再開では world snapshot の subsystem 欠落を fail-fast にする。"""
        from ai_rpg_world.application.being.being_snapshot_file_gateway import WorldStateSnapshotFileGateway
        from ai_rpg_world.application.being.world_state_snapshot import (
            WorldStateSnapshot,
            WorldStateSnapshotCoverageError,
        )

        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        WorldStateSnapshotFileGateway().write(
            WorldStateSnapshot(
                source_scenario="demo",
                world_tick=10,
                subsystems={"world_tick": {"schema_version": 1, "world_tick": 10}},
            ),
            tmp_path / "snap",
        )
        with pytest.raises(WorldStateSnapshotCoverageError, match="missing"):
            session.restore_world_from_dir(
                runtime=SimpleNamespace(), input_dir=tmp_path / "snap", current_scenario="demo"
            )

    def test_metadata_legacy_snapshot_restore_works(self, tmp_path: Path) -> None:
        """``_metadata`` キー無しの旧 snapshot ファイルでも壊れない (後方互換)。"""
        from ai_rpg_world.application.being.being_snapshot_file_gateway import BeingSnapshotFileGateway
        from ai_rpg_world.being.domain.persona import Persona
        from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot

        snap_dir = tmp_path / "old"
        snap_dir.mkdir()
        gateway = BeingSnapshotFileGateway()
        snap = BeingSnapshot(
            being_id_value="being_w1_p1",
            persona=Persona(name="agent"),
            attachment_environment_id="w1p1",
            attachment_environment_name="廃坑の山村",
            snapshot_version=2,
            memory_payload_json=None,
        )
        gateway.write(snap, snap_dir / "being_w1_p1.json")
        (wiring, _) = _make_wiring_stub()
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        report = session.restore_all_from_dir(snap_dir, current_scenario="anything")
        assert len(report.restored) == 1
        assert report.cross_scenario_transfers == []
        assert all(v is None for v in report.metadata_by_being.values())


class TestMemoryTurns:
    """SNAPSHOT_SAVE / SNAPSHOT_LOAD の trace に載せる記憶のターン数を、Being ごとに返す挙動を保証する。"""

    def test_returns_memory_turn_per_given_being(self, tmp_path: Path) -> None:
        """渡した Being の順に、記憶のターン数を返す。ターンが進んでいない Being は 0。"""
        rio, noa = BeingId("being-rio"), BeingId("being-noa")
        (wiring, _) = _make_wiring_stub()
        wiring.memory_turn_clock.advance_turn(rio)
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")

        turns = session.memory_turns([rio, noa])

        assert turns == [
            {"being_id": "being-rio", "memory_turn": 1},
            {"being_id": "being-noa", "memory_turn": 0},
        ]


class TestPlayerBeingsOnResume:
    """再開したとき、誰がどのプレイヤーを動かしているかを世界の snapshot か Being の snapshot から読むことを保証する (design_decisions D1928)。

    実際の run と同じく、再開する側でも先にシナリオのプレイヤーへ Being を用意してから読む。
    """

    @staticmethod
    def _being_snapshots(tmp_path: Path, *player_values: int) -> Path:
        """``player_values`` のプレイヤーを動かす Being を用意し、その Being の snapshot を書き出したディレクトリ。"""
        (wiring, provisioning) = _make_wiring_stub()
        for value in player_values:
            provisioning.ensure_attached(PlayerId(value))
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=tmp_path / "snap")
        session.capture_all([PlayerId(value) for value in player_values])
        return tmp_path / "snap"

    @staticmethod
    def _as_old_format(snap_dir: Path) -> None:
        """Being の snapshot を、居場所を世界とプレイヤーの番号で持っていた古い形に書き換える。"""
        import json

        for path in snap_dir.glob("being_w1_p*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("attachment_environment_id")
            data.pop("attachment_environment_name")
            data["attachment_world_id"] = 1
            data["attachment_player_id"] = int(path.stem.removeprefix("being_w1_p"))
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _resume(snap_dir: Path, *player_values: int) -> tuple[SimpleNamespace, ExperimentSnapshotSession]:
        """``player_values`` のプレイヤーに起動時の Being を用意してから、``snap_dir`` の Being の snapshot を読む。"""
        from ai_rpg_world.application.being.world_state_snapshot_service import WorldStateSnapshotService
        from ai_rpg_world.application.being.world_subsystems.player_beings_codec import PlayerBeingsSubsystemCodec

        (wiring, provisioning) = _make_wiring_stub()
        for value in player_values:
            provisioning.ensure_attached(PlayerId(value))
        session = ExperimentSnapshotSession(wiring_result=wiring, snapshot_dir=snap_dir)
        session._world_snapshot_service = WorldStateSnapshotService(
            subsystem_codecs=[PlayerBeingsSubsystemCodec()], expected_subsystem_keys=("player_beings",)
        )
        session.restore_all_from_dir(snap_dir)
        return wiring, session

    @staticmethod
    def _write_world(snap_dir: Path, pairs: list[tuple[int, str]] | None) -> None:
        from ai_rpg_world.application.being.being_snapshot_file_gateway import WorldStateSnapshotFileGateway
        from ai_rpg_world.application.being.world_state_snapshot import WorldStateSnapshot

        subsystems = (
            {}
            if pairs is None
            else {
                "player_beings": {
                    "schema_version": 1,
                    "pairs": [{"player_id": player, "being_id": being} for player, being in pairs],
                }
            }
        )
        WorldStateSnapshotFileGateway().write(
            WorldStateSnapshot(source_scenario="demo", world_tick=3, subsystems=subsystems), snap_dir
        )

    @staticmethod
    def _restore_world(wiring: SimpleNamespace, session: ExperimentSnapshotSession, snap_dir: Path) -> None:
        session.restore_world_from_dir(
            SimpleNamespace(_player_beings=wiring.player_beings), snap_dir, current_scenario="demo"
        )

    def test_table_in_the_world_snapshot_is_used(self, tmp_path: Path) -> None:
        """世界の snapshot に対応表があれば、それで続け、読んだ先を world_snapshot と残す。"""
        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        self._write_world(snap_dir, [(1, "being_w1_p1"), (2, "being_w1_p2")])
        wiring, session = self._resume(snap_dir, 1, 2)

        self._restore_world(wiring, session, snap_dir)

        assert wiring.player_beings.pairs() == (
            (PlayerId(1), BeingId("being_w1_p1")),
            (PlayerId(2), BeingId("being_w1_p2")),
        )
        assert session.player_beings_source == "world_snapshot"

    def test_old_world_snapshot_without_the_table_uses_being_numbers(self, tmp_path: Path) -> None:
        """対応表の欄が無い古い世界の snapshot は、古い Being の snapshot に残る番号の対応表で続ける。"""
        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        self._as_old_format(snap_dir)
        self._write_world(snap_dir, None)
        wiring, session = self._resume(snap_dir, 1, 2)

        self._restore_world(wiring, session, snap_dir)

        assert wiring.player_beings.being_of(PlayerId(2)) == BeingId("being_w1_p2")
        assert session.player_beings_source == "being_snapshots"

    def test_no_world_snapshot_uses_being_numbers(self, tmp_path: Path) -> None:
        """世界の snapshot が無い古い snapshot も、古い Being の snapshot に残る番号で続ける。"""
        snap_dir = self._being_snapshots(tmp_path, 1)
        self._as_old_format(snap_dir)
        wiring, session = self._resume(snap_dir, 1)

        assert session.restore_world_from_dir(None, snap_dir, current_scenario="demo") is None

        assert wiring.player_beings.being_of(PlayerId(1)) == BeingId("being_w1_p1")
        assert session.player_beings_source == "being_snapshots"

    def test_player_not_in_this_run_is_skipped(self, tmp_path: Path) -> None:
        """古い Being の snapshot が、今の run にいないプレイヤーを指していれば、対応表に載せずに続ける。"""
        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        self._as_old_format(snap_dir)
        wiring, session = self._resume(snap_dir, 1)

        session.restore_world_from_dir(None, snap_dir, current_scenario="demo")

        assert wiring.player_beings.pairs() == ((PlayerId(1), BeingId("being_w1_p1")),)

    def test_two_beings_driving_one_player_stop_before_starting(self, tmp_path: Path) -> None:
        """2 つの Being の snapshot が同じプレイヤーを指していれば、読み込みの時点で止める。"""
        import json

        from ai_rpg_world.domain.world.exception.player_beings_exception import PlayerAlreadyDrivenException

        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        self._as_old_format(snap_dir)
        second = snap_dir / "being_w1_p2.json"
        data = json.loads(second.read_text(encoding="utf-8"))
        data["attachment_player_id"] = 1
        second.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(PlayerAlreadyDrivenException):
            self._resume(snap_dir, 1, 2)

    def test_world_table_disagreeing_with_being_numbers_stops(self, tmp_path: Path) -> None:
        """世界の snapshot の対応表が、Being の snapshot の番号と食い違えば、起動前に止める。"""
        from ai_rpg_world.application.being.world_state_snapshot import WorldStateSnapshotCoverageError

        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        self._as_old_format(snap_dir)
        self._write_world(snap_dir, [(1, "being_w1_p2"), (2, "being_w1_p1")])
        wiring, session = self._resume(snap_dir, 1, 2)

        with pytest.raises(WorldStateSnapshotCoverageError, match="食い違います"):
            self._restore_world(wiring, session, snap_dir)

    def test_world_table_naming_a_being_without_snapshot_stops(self, tmp_path: Path) -> None:
        """世界の snapshot の対応表に、snapshot の無い Being が載っていれば止める。起動時の記憶の無い Being で黙って始めないため。"""
        from ai_rpg_world.application.being.world_state_snapshot import WorldStateSnapshotCoverageError

        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        (snap_dir / "being_w1_p2.json").unlink()
        self._write_world(snap_dir, [(1, "being_w1_p1"), (2, "being_w1_p2")])
        wiring, session = self._resume(snap_dir, 1, 2)

        with pytest.raises(WorldStateSnapshotCoverageError, match="being_w1_p2"):
            self._restore_world(wiring, session, snap_dir)

    def test_resumed_beings_enter_this_environment(self, tmp_path: Path) -> None:
        """別の環境で保存した Being も、居場所の無い古い Being も、対応表でこの run のプレイヤーを動かすなら、この run の環境に入る。"""
        import json

        snap_dir = self._being_snapshots(tmp_path, 1, 2)
        first = snap_dir / "being_w1_p1.json"
        data = json.loads(first.read_text(encoding="utf-8"))
        data["attachment_environment_id"] = "other_world#1"
        first.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        second = snap_dir / "being_w1_p2.json"
        data = json.loads(second.read_text(encoding="utf-8"))
        data.pop("attachment_environment_id")
        data.pop("attachment_environment_name")
        second.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self._write_world(snap_dir, [(1, "being_w1_p1"), (2, "being_w1_p2")])
        wiring, session = self._resume(snap_dir, 1, 2)

        self._restore_world(wiring, session, snap_dir)

        for being_id in ("being_w1_p1", "being_w1_p2"):
            assert wiring.being_repository.find_by_id(BeingId(being_id)).attachment == _ENVIRONMENT

    def test_old_being_of_another_world_listed_in_the_table_stops(self, tmp_path: Path) -> None:
        """別の世界の番号を持つ古い Being が、世界の snapshot の対応表でこの run のプレイヤーに載っていれば、食い違いとして止める。"""
        import json

        from ai_rpg_world.application.being.world_state_snapshot import WorldStateSnapshotCoverageError

        snap_dir = self._being_snapshots(tmp_path, 1)
        self._as_old_format(snap_dir)
        path = snap_dir / "being_w1_p1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["attachment_world_id"] = 2
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self._write_world(snap_dir, [(1, "being_w1_p1")])
        wiring, session = self._resume(snap_dir, 1)

        with pytest.raises(WorldStateSnapshotCoverageError, match="食い違います"):
            self._restore_world(wiring, session, snap_dir)
