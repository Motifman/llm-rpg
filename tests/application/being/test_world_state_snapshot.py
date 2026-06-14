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
    WorldStateSnapshot,
    WorldStateSnapshotVersionError,
)
from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldStateSnapshotService,
    WorldSubsystemCodec,
)


class TestWorldStateSnapshotVO:
    """VO の不変条件挙動。"""

    def test_最小構成で生成できる(self) -> None:
        s = WorldStateSnapshot(source_scenario="demo", world_tick=0)
        assert s.source_scenario == "demo"
        assert s.world_tick == 0
        assert s.subsystems == {}
        assert s.schema_version == 1

    def test_空_source_scenario_は_例外(self) -> None:
        with pytest.raises(ValueError, match="source_scenario"):
            WorldStateSnapshot(source_scenario="", world_tick=0)

    def test_負の_world_tick_は_例外(self) -> None:
        with pytest.raises(ValueError, match="world_tick"):
            WorldStateSnapshot(source_scenario="demo", world_tick=-1)

    def test_bool_world_tick_は_例外(self) -> None:
        """``True`` は int 派生だが意図的に弾く (= 既存 BeingSnapshot 同方針)。"""
        with pytest.raises(ValueError, match="world_tick"):
            WorldStateSnapshot(
                source_scenario="demo", world_tick=True  # type: ignore[arg-type]
            )

    def test_0以下の_schema_version_は_例外(self) -> None:
        with pytest.raises(ValueError, match="schema_version"):
            WorldStateSnapshot(
                source_scenario="demo", world_tick=0, schema_version=0
            )

    def test_to_dict_と_from_dict_の_round_trip(self) -> None:
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

    def test_codec_未登録なら_subsystems_は_空(self) -> None:
        service = WorldStateSnapshotService()
        snapshot = service.capture(
            runtime=SimpleNamespace(),
            source_scenario="demo",
            world_tick=10,
        )
        assert snapshot.subsystems == {}

    def test_登録済_codec_が_capture_に呼ばれる(self) -> None:
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snapshot = service.capture(
            runtime=SimpleNamespace(),
            source_scenario="demo",
            world_tick=10,
        )
        assert codec.capture_count == 1
        assert snapshot.subsystems == {"player_status": {"hello": "world"}}

    def test_重複_subsystem_key_は_constructor_エラー(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            WorldStateSnapshotService(
                subsystem_codecs=[
                    _RecordingCodec("a"),
                    _RecordingCodec("a"),
                ]
            )


class TestWorldStateSnapshotServiceRestore:
    """restore の挙動 (scenario / version / unknown subsystem)。"""

    def test_codec_が_restore_に呼ばれる(self) -> None:
        codec = _RecordingCodec("player_status")
        service = WorldStateSnapshotService(subsystem_codecs=[codec])
        snap = WorldStateSnapshot(
            source_scenario="demo",
            world_tick=5,
            subsystems={"player_status": {"x": 1}},
        )
        service.restore(SimpleNamespace(), snap, current_scenario="demo")
        assert codec.restore_calls == [{"x": 1}]

    def test_未サポート_schema_version_は_例外(self) -> None:
        service = WorldStateSnapshotService()
        snap = WorldStateSnapshot(
            source_scenario="demo", world_tick=0, schema_version=99
        )
        with pytest.raises(WorldStateSnapshotVersionError):
            service.restore(SimpleNamespace(), snap, current_scenario="demo")

    def test_scenario_不一致は_fail_fast(self) -> None:
        service = WorldStateSnapshotService()
        snap = WorldStateSnapshot(source_scenario="forest", world_tick=0)
        with pytest.raises(WorldStateScenarioMismatchError, match="forest"):
            service.restore(SimpleNamespace(), snap, current_scenario="desert")

    def test_未知_subsystem_は_skip_される(
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

    def test_registered_subsystem_keys_を取れる(self) -> None:
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

    def test_exists_in_の_前後(self, tmp_path: Path) -> None:
        gateway = WorldStateSnapshotFileGateway()
        assert gateway.exists_in(tmp_path) is False
        gateway.write(
            WorldStateSnapshot(source_scenario="d", world_tick=0), tmp_path
        )
        assert gateway.exists_in(tmp_path) is True

    def test_read_は_ファイルなしで_FileNotFoundError(
        self, tmp_path: Path
    ) -> None:
        gateway = WorldStateSnapshotFileGateway()
        with pytest.raises(FileNotFoundError):
            gateway.read(tmp_path)

    def test_書き出した_JSON_は_human_readable(self, tmp_path: Path) -> None:
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
