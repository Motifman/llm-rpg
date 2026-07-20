"""WorldStateSnapshot + WorldStateSnapshotService の基盤テスト (Phase 9-1)。

中身の subsystem codec は Phase 9-2 以降で追加されるため、本 PR では
**器の挙動だけ** をテストする:

- VO の不変条件 (= 空 source_scenario / 負の tick / 未サポート version)
- service の capture / restore round-trip (= subsystems が空でも OK)
- subsystem mismatch / scenario mismatch / version mismatch のエラー処理
- 後方互換: 旧 snapshot directory (= world.json 無し) でも壊れない
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    WorldStateSnapshotFileGateway,
)
from ai_rpg_world.application.being.world_state_snapshot import (
    SUPPORTED_WORLD_SNAPSHOT_VERSIONS,
    WorldStateScenarioMismatchError,
    WorldStateSnapshotCoverageError,
    WorldStateSnapshot,
    WorldStateSnapshotVersionError,
)
from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldStateSnapshotService,
    WorldSubsystemCodec,
)


class TestWorldStateSnapshotVO:
    """VO の不変条件挙動。"""

    def test_min_can_create(self) -> None:
        """最小構成で生成できる。"""
        s = WorldStateSnapshot(source_scenario="demo", world_tick=0)
        assert s.source_scenario == "demo"
        assert s.world_tick == 0
        assert s.subsystems == {}
        assert s.schema_version == 2

    def test_empty_source_scenario_raises_exception(self) -> None:
        """空 sourcescenario は例外。"""
        with pytest.raises(ValueError, match="source_scenario"):
            WorldStateSnapshot(source_scenario="", world_tick=0)

    def test_negative_world_tick_raises_exception(self) -> None:
        """負の worldtick は例外。"""
        with pytest.raises(ValueError, match="world_tick"):
            WorldStateSnapshot(source_scenario="demo", world_tick=-1)

    def test_bool_world_tick_raises_exception(self) -> None:
        """``True`` は int 派生だが意図的に弾く (= 既存 BeingSnapshot 同方針)。"""
        with pytest.raises(ValueError, match="world_tick"):
            WorldStateSnapshot(
                source_scenario="demo", world_tick=True  # type: ignore[arg-type]
            )

    def test_zero_schema_version_raises_exception(self) -> None:
        """0 以下の schemaversion は例外。"""
        with pytest.raises(ValueError, match="schema_version"):
            WorldStateSnapshot(
                source_scenario="demo", world_tick=0, schema_version=0
            )

    def test_dict_round_trip(self) -> None:
        """to dict と from dict の round trip。"""
        s = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=42,
            subsystems={"player_status": {"v": 1}},
            captured_at="2026-06-14T12:00:00+00:00",
        )
        restored = WorldStateSnapshot.from_dict(s.to_dict())
        assert restored == s


class _RecordingCodec(WorldSubsystemCodec):
    """test 用 codec — capture / restore の呼出を記録する。"""

    def __init__(
        self, key: str, capture_payload: dict[str, Any] | None = None
    ) -> None:
        self._key = key
        self.capture_count = 0
        self.restore_calls: list[dict[str, Any]] = []
        self._payload = capture_payload or {"hello": "world"}

    @property
    def subsystem_key(self) -> str:
        return self._key

    def capture(self, runtime: Any) -> dict[str, Any]:
        self.capture_count += 1
        return dict(self._payload)

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        self.restore_calls.append(data)


class TestWorldStateSnapshotServiceCapture:
    """capture の挙動。"""

    def test_unregistered_codec_keeps_subsystems_empty(self) -> None:
        """codec 未登録なら subsystems は空。"""
        service = WorldStateSnapshotService()
        snapshot = service.capture(
            runtime=SimpleNamespace(),
            source_scenario="demo",
            world_tick=10,
        )
        assert snapshot.subsystems == {}

    def test_calls_codec_capture(self) -> None:
        """登録済 codec が capture に呼ばれる。"""
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snapshot = service.capture(
            runtime=SimpleNamespace(),
            source_scenario="demo",
            world_tick=10,
        )
        assert codec.capture_count == 1
        assert snapshot.subsystems == {"player_status": {"hello": "world"}}

    def test_duplicate_subsystem_key_constructor_error(self) -> None:
        """重複 subsystem key は constructor エラー。"""
        with pytest.raises(ValueError, match="duplicate"):
            WorldStateSnapshotService(
                subsystem_codecs=[
                    _RecordingCodec("a"),
                    _RecordingCodec("a"),
                ]
            )

    def test_expected_subsystem_keys_mismatch_constructor_error(self) -> None:
        """期待 key と登録 codec が違う場合は構築時に例外にする。"""
        with pytest.raises(WorldStateSnapshotCoverageError, match="expected"):
            WorldStateSnapshotService(
                subsystem_codecs=[_RecordingCodec("player_status")],
                expected_subsystem_keys=["player_status", "world_tick"],
            )


class TestWorldStateSnapshotServiceRestore:
    """restore の挙動 (scenario / version / unknown subsystem)。"""

    def test_calls_codec_restore(self) -> None:
        """codec が restore に呼ばれる。"""
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=5,
            subsystems={"player_status": {"x": 1}},
        )
        service.restore(SimpleNamespace(), snap, current_scenario="demo")
        assert codec.restore_calls == [{"x": 1}]

    def test_unsupported_schema_version_raises_exception(self) -> None:
        """未サポート schemaversion は例外。"""
        service = WorldStateSnapshotService()
        snap = WorldStateSnapshot(
            source_scenario="demo", world_tick=0, schema_version=99
        )
        with pytest.raises(WorldStateSnapshotVersionError):
            service.restore(SimpleNamespace(), snap, current_scenario="demo")

    def test_strict_restore_legacy_schema_version_raises_exception(self) -> None:
        """strict restore では旧 world snapshot schema を実験再開に使わない。"""
        codec = _RecordingCodec("world_tick")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=0,
            schema_version=1,
            subsystems={"world_tick": {"x": 1}},
        )
        with pytest.raises(WorldStateSnapshotVersionError, match="strict"):
            service.restore(
                SimpleNamespace(),
                snap,
                current_scenario="demo",
                strict_subsystems=True,
            )

    def test_non_strict_restore_legacy_schema_version_works(self) -> None:
        """通常 restore では旧 world snapshot schema を後方互換で読める。"""
        codec = _RecordingCodec("world_tick")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=0,
            schema_version=1,
            subsystems={"world_tick": {"x": 1}},
        )
        service.restore(SimpleNamespace(), snap, current_scenario="demo")
        assert codec.restore_calls == [{"x": 1}]

    def test_scenario_matches_fail_fast(self) -> None:
        """scenario 不一致は fail fast。"""
        service = WorldStateSnapshotService()
        snap = WorldStateSnapshot(source_scenario="forest", world_tick=0)
        with pytest.raises(WorldStateScenarioMismatchError, match="forest"):
            service.restore(SimpleNamespace(), snap, current_scenario="desert")

    def test_unknown_subsystem_skip(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """新 version で増えた subsystem を旧 code で読む場合の後方互換。"""
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=0,
            subsystems={
                "player_status": {"x": 1},
                "future_subsystem": {"y": 2},
            },
        )
        with caplog.at_level("INFO"):
            service.restore(SimpleNamespace(), snap, current_scenario="demo")
        # 登録済 codec は呼ばれる
        assert codec.restore_calls == [{"x": 1}]
        # 未知 subsystem は info ログ
        assert any(
            "future_subsystem" in r.message for r in caplog.records
        )

    def test_strict_unknown_subsystem_raises_exception(self) -> None:
        """strict restore では未登録 subsystem を読み飛ばさず例外にする。"""
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=0,
            subsystems={
                "player_status": {"x": 1},
                "future_subsystem": {"y": 2},
            },
        )
        with pytest.raises(
            WorldStateSnapshotCoverageError, match="future_subsystem"
        ):
            service.restore(
                SimpleNamespace(),
                snap,
                current_scenario="demo",
                strict_subsystems=True,
            )

    def test_strict_missing_expected_subsystem_raises_exception(self) -> None:
        """strict restore では期待 subsystem 欠落を例外にする。"""
        codec = _RecordingCodec("player_status")
        tick_codec = _RecordingCodec("world_tick")
        service = WorldStateSnapshotService(
            subsystem_codecs=[codec, tick_codec],
            expected_subsystem_keys=["player_status", "world_tick"],
        )
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=0,
            subsystems={"player_status": {"x": 1}},
        )
        with pytest.raises(WorldStateSnapshotCoverageError, match="world_tick"):
            service.restore(
                SimpleNamespace(),
                snap,
                current_scenario="demo",
                strict_subsystems=True,
            )

    def test_registered_subsystem_keys_can_get(self) -> None:
        """registered subsystem keys を取れる。"""
        service = WorldStateSnapshotService(
            subsystem_codecs=[
                _RecordingCodec("a"),
                _RecordingCodec("b"),
            ]
        )
        assert service.registered_subsystem_keys == ["a", "b"]


class TestWorldStateSnapshotFileGateway:
    """world.json の read / write。"""

    def test_write_read_round_trip(self, tmp_path: Path) -> None:
        gateway = WorldStateSnapshotFileGateway()
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=30,
            subsystems={"x": {"value": 1}},
        )
        gateway.write(snap, tmp_path)
        loaded = gateway.read(tmp_path)
        assert loaded == snap

    def test_exists_around(self, tmp_path: Path) -> None:
        """existsin の前後。"""
        gateway = WorldStateSnapshotFileGateway()
        assert gateway.exists_in(tmp_path) is False
        gateway.write(
            WorldStateSnapshot(source_scenario="d", world_tick=0), tmp_path
        )
        assert gateway.exists_in(tmp_path) is True

    def test_read_raises_file_not_found_error(
        self, tmp_path: Path
    ) -> None:
        """read はファイルなしで FileNotFoundError。"""
        gateway = WorldStateSnapshotFileGateway()
        with pytest.raises(FileNotFoundError):
            gateway.read(tmp_path)

    def test_written_json_human_readable(self, tmp_path: Path) -> None:
        """書き出した JSON は human readable。"""
        gateway = WorldStateSnapshotFileGateway()
        gateway.write(
            WorldStateSnapshot(source_scenario="森の世界", world_tick=42),
            tmp_path,
        )
        raw = (tmp_path / "world.json").read_text(encoding="utf-8")
        # 日本語 scenario 名がそのまま入る
        assert "森の世界" in raw
        data = json.loads(raw)
        assert data["world_tick"] == 42
