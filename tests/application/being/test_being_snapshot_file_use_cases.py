"""capture / restore use case の round-trip 挙動 (Phase 5)。"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import BeingMemorySnapshotService
from ai_rpg_world.application.being.being_snapshot_file_gateway import BeingSnapshotFileGateway
from ai_rpg_world.application.being.capture_being_snapshot_to_file_use_case import (
    BeingNotFoundForSnapshotError,
    CaptureBeingSnapshotToFileUseCase,
)
from ai_rpg_world.application.being.restore_being_snapshot_from_file_use_case import RestoreBeingSnapshotFromFileUseCase
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import InMemoryShortTermMemoryRepository
from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository


def _make_environment():
    """新規 store 群 + 2 use case + gateway を組んで返す。"""
    repo = InMemoryBeingRepository()
    acquaintances = InMemoryAcquaintanceRepository()
    memory_snapshot = BeingMemorySnapshotService(
        acquaintance_store=acquaintances,
        being_episode_store=InMemoryEpisodeRepository(),
        being_memo_store=InMemoryMemoBookRepository(),
        memory_turn_clock=InMemoryMemoryTurnClock(),
        being_short_term_memory_store=InMemoryShortTermMemoryRepository(),
    )
    gateway = BeingSnapshotFileGateway()
    capture = CaptureBeingSnapshotToFileUseCase(
        being_repository=repo, memory_snapshot_service=memory_snapshot, file_gateway=gateway
    )
    restore = RestoreBeingSnapshotFromFileUseCase(
        being_repository=repo, memory_snapshot_service=memory_snapshot, file_gateway=gateway
    )
    return {"repo": repo, "acquaintances": acquaintances, "capture": capture, "restore": restore}


def _make_being() -> Being:
    return Being(
        being_id=BeingId("being_w1_p1"),
        identity=BeingIdentity(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(world_id=WorldId(1), player_id=PlayerId(1)),
        declared_memory_kinds=[MemoryKind.MEMO, MemoryKind.SHORT_TERM],
    )


class TestCaptureUseCase:
    def test_unregistered_being_raises_exception(self, tmp_path: Path) -> None:
        """未登録 being は例外。"""
        env = _make_environment()
        with pytest.raises(BeingNotFoundForSnapshotError):
            env["capture"].execute(BeingId("missing"), tmp_path / "x.json")

    def test_writes_repo_does_not_change_capture_file(self, tmp_path: Path) -> None:
        """capture はファイルを書き出し repo を変更しない。"""
        env = _make_environment()
        being = _make_being()
        env["repo"].save(being)
        env["acquaintances"].record_meeting(being.being_id, environment_name="島", name="カイト", turn=1)
        out = tmp_path / "snap.json"
        result = env["capture"].execute(being.being_id, out)
        assert out.exists()
        assert result.snapshot_version == 2
        assert result.has_memory_payload is True
        snap = env["repo"].find_snapshot_by_id(being.being_id)
        assert snap is not None
        assert snap.has_memory_payload is False


class TestRestoreUseCase:
    def test_capture_restore_memory_restored(self, tmp_path: Path) -> None:
        """source 側 → file → 別 dst 環境への完全 round-trip。"""
        src = _make_environment()
        being = _make_being()
        src["repo"].save(being)
        src["acquaintances"].record_meeting(being.being_id, environment_name="島", name="カイト", turn=1)
        snap_path = tmp_path / "snap.json"
        src["capture"].execute(being.being_id, snap_path)
        dst = _make_environment()
        result = dst["restore"].execute(snap_path)
        assert result.memory_restored is True
        assert [a.name for a in dst["acquaintances"].list_by_being(being.being_id)] == ["カイト"]
        loaded = dst["repo"].find_by_id(being.being_id)
        assert loaded is not None
        assert loaded.identity.name == "アダ"

    def test_payload_snapshot_restore_memory(self, tmp_path: Path) -> None:
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
        assert env["repo"].find_snapshot_by_id(BeingId("being_w1_p1")) is not None


class TestConstructorTypeGuards:
    def test_capture_constructor_raises_type_error(self) -> None:
        """capture constructor 型違反。"""
        with pytest.raises(TypeError, match="being_repository"):
            CaptureBeingSnapshotToFileUseCase(
                being_repository="bad",
                memory_snapshot_service=_make_environment()["capture"]._memory,
                file_gateway=BeingSnapshotFileGateway(),
            )

    def test_restore_constructor_raises_type_error(self) -> None:
        """restore constructor 型違反。"""
        with pytest.raises(TypeError, match="file_gateway"):
            RestoreBeingSnapshotFromFileUseCase(
                being_repository=InMemoryBeingRepository(),
                memory_snapshot_service=_make_environment()["capture"]._memory,
                file_gateway="bad",
            )

    def test_execute_argument_raises_type_error(self, tmp_path: Path) -> None:
        """execute の引数型違反。"""
        env = _make_environment()
        with pytest.raises(TypeError):
            env["capture"].execute("ada", tmp_path / "x.json")
        with pytest.raises(TypeError):
            env["capture"].execute(BeingId("x"), "string-not-path")
        with pytest.raises(TypeError):
            env["restore"].execute("string-not-path")


_OLD_MEMORY_KEYS = {
    "memo": [
        {"id": "m1", "content": "井戸は北", "added_at_tick": 90},
        {"id": "m2", "content": "鍵を探す", "added_at_tick": 91},
        {"id": "m3", "content": "火を絶やさない", "added_at_tick": None},
    ],
    "pending_predictions": [{"pending_id": "p1", "tick_from": 20, "tick_to": 25}],
    "afterglow_entries": [{"episode_id": "e3", "entered_tick": 85}],
}


def _capture_old_snapshot(tmp_path: Path, old_keys: dict[str, object]) -> Path:
    """知り合いを 1 人持つ Being を capture し、消した部品の欄を memory payload に書き足す。"""
    env = _make_environment()
    being = _make_being()
    env["repo"].save(being)
    env["acquaintances"].record_meeting(being.being_id, environment_name="島", name="カイト", turn=3)
    path = tmp_path / "being.json"
    env["capture"].execute(being.being_id, path)
    gateway = BeingSnapshotFileGateway()
    snapshot = gateway.read(path)
    payload = {**json.loads(snapshot.memory_payload_json), **old_keys}
    gateway.write(dataclasses.replace(snapshot, memory_payload_json=json.dumps(payload)), path)
    return path


class TestRestoreUseCaseDropsRemovedMemoryKeys:
    """消した部品の欄を持つ古い snapshot を、拒まずに捨てて読み込み、捨てた件数を報告する挙動を保証する。"""

    def test_old_snapshot_is_restored_and_dropped_keys_are_counted(self, tmp_path: Path) -> None:
        """古いメモ・約束・余韻の欄を持つ snapshot は、止まらずに読み込まれ、欄ごとの件数が報告され、ほかの記憶は戻る。"""
        path = _capture_old_snapshot(tmp_path, _OLD_MEMORY_KEYS)
        dst = _make_environment()

        result = dst["restore"].execute(path)

        assert result.removed_memory_key_counts == {"memo": 3, "pending_predictions": 1, "afterglow_entries": 1}
        assert [a.name for a in dst["acquaintances"].list_by_being(BeingId("being_w1_p1"))] == ["カイト"]

    def test_snapshot_without_removed_keys_reports_nothing(self, tmp_path: Path) -> None:
        """消した部品の欄を持たない snapshot は、捨てた件数を空で報告する。"""
        path = _capture_old_snapshot(tmp_path, {})
        dst = _make_environment()

        result = dst["restore"].execute(path)

        assert result.removed_memory_key_counts == {}


class TestRestoreRemovedDeclaration:
    """ファイル復元で廃止済みの宣言と記憶本文を分けて扱う。"""

    def test_removed_declarations_are_counted_without_changing_memory_payload(self, tmp_path: Path) -> None:
        """semantic宣言2件を除去して報告し、記憶本文をそのまま保存・復元する。"""
        path = _capture_old_snapshot(tmp_path, {})
        gateway = BeingSnapshotFileGateway()
        snapshot = dataclasses.replace(gateway.read(path), declared_memory_kinds=("memo", "semantic", "semantic"))
        gateway.write(snapshot, path)
        dst = _make_environment()
        result = dst["restore"].execute(path)
        assert result.removed_declared_memory_kind_counts == {"semantic": 2}
        assert result.removed_memory_key_counts == {}
        stored = dst["repo"].find_snapshot_by_id(result.being_id)
        assert stored.declared_memory_kinds == ("memo",)
        assert stored.memory_payload_json == snapshot.memory_payload_json
        assert [a.name for a in dst["acquaintances"].list_by_being(result.being_id)] == ["カイト"]

    def test_unknown_declaration_is_rejected_before_saving(self, tmp_path: Path) -> None:
        """semanticと未知の宣言が混在するファイルは、保存先に書き込む前に拒否する。"""
        from ai_rpg_world.domain.being.exception.being_exceptions import BeingSnapshotIncompleteException

        path = _capture_old_snapshot(tmp_path, {})
        gateway = BeingSnapshotFileGateway()
        gateway.write(dataclasses.replace(gateway.read(path), declared_memory_kinds=("semantic", "unknown_kind")), path)
        dst = _make_environment()
        with pytest.raises(BeingSnapshotIncompleteException, match="unknown_kind"):
            dst["restore"].execute(path)
        assert dst["repo"].find_snapshot_by_id(BeingId("being_w1_p1")) is None

    def test_current_snapshot_reports_no_removed_declarations(self, tmp_path: Path) -> None:
        """現役の宣言だけのファイルでは、除去した宣言の件数を空で報告する。"""
        path = _capture_old_snapshot(tmp_path, {})
        assert _make_environment()["restore"].execute(path).removed_declared_memory_kind_counts == {}
