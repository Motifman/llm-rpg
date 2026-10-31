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
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import InMemoryShortTermMemoryRepository
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
        persona=Persona(name="アダ", first_person="わたし"),
        attachment=BeingAttachment(world_id=1, player_id=1),
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
        assert loaded.persona.name == "アダ"

    def test_payload_snapshot_restore_memory(self, tmp_path: Path) -> None:
        """v1 snapshot 想定: memory_payload_json=None なら memory_restored=False。"""
        from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot

        env = _make_environment()
        snap = BeingSnapshot(
            being_id_value="being_w1_p1",
            persona=Persona(name="アダ", first_person="わたし"),
            attachment_world_id=1,
            attachment_player_id=1,
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
    """古いファイルに残る記憶の種類の宣言を、記憶本文とは分けて数え、読み捨てることを保証する (design_decisions D1469-1)。"""

    @staticmethod
    def _declare_in_file(path: Path, kinds: list[str]) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["declared_memory_kinds"] = kinds
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_removed_declarations_are_counted_without_changing_memory_payload(self, tmp_path: Path) -> None:
        """宣言をどの種類も数えて報告し、保存した snapshot には残さず、記憶本文はそのまま復元する。"""
        path = _capture_old_snapshot(tmp_path, {})
        self._declare_in_file(path, ["memo", "semantic", "semantic", "unknown_kind"])
        payload = BeingSnapshotFileGateway().read(path).memory_payload_json
        dst = _make_environment()

        result = dst["restore"].execute(path)

        assert result.removed_declared_memory_kind_counts == {"memo": 1, "semantic": 2, "unknown_kind": 1}
        assert result.removed_memory_key_counts == {}
        stored = dst["repo"].find_snapshot_by_id(result.being_id)
        assert stored.legacy_declared_memory_kinds == ()
        assert stored.memory_payload_json == payload
        assert [a.name for a in dst["acquaintances"].list_by_being(result.being_id)] == ["カイト"]

    def test_current_snapshot_reports_no_removed_declarations(self, tmp_path: Path) -> None:
        """宣言を持たない今のファイルでは、読み捨てた宣言の件数を空で報告する。"""
        path = _capture_old_snapshot(tmp_path, {})
        assert _make_environment()["restore"].execute(path).removed_declared_memory_kind_counts == {}


class TestRestoreLegacyIdentity:
    """persona の無い古いファイルの名前と一人称を読み捨て、起動時に入れた人柄で復元することを保証する (design_decisions D1469-2)。"""

    @staticmethod
    def _make_legacy(path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["persona"]
        data.update(identity_name="agent_1", identity_first_person="わたし")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_legacy_identity_is_dropped_and_current_persona_is_kept(self, tmp_path: Path) -> None:
        """復元先にシナリオから用意した Being があれば、その人柄を残し、読み捨てた名前と一人称を結果で返す。記憶は戻る。"""
        path = _capture_old_snapshot(tmp_path, {})
        self._make_legacy(path)
        dst = _make_environment()
        scenario_persona = Persona(name="ハル")
        dst["repo"].save(
            Being(
                being_id=BeingId("being_w1_p1"),
                persona=scenario_persona,
                attachment=BeingAttachment(world_id=1, player_id=1),
            )
        )

        result = dst["restore"].execute(path)

        assert result.removed_legacy_identity == {"name": "agent_1", "first_person": "わたし"}
        stored = dst["repo"].find_snapshot_by_id(BeingId("being_w1_p1"))
        assert stored.persona == scenario_persona
        assert (stored.legacy_identity_name, stored.legacy_identity_first_person) == (None, None)
        assert [a.name for a in dst["acquaintances"].list_by_being(BeingId("being_w1_p1"))] == ["カイト"]

    def test_legacy_identity_without_a_being_to_take_from_is_rejected(self, tmp_path: Path) -> None:
        """復元先に人柄を引ける Being が無ければ、保存先に書く前に BeingSnapshotIncompleteException で断る。"""
        from ai_rpg_world.domain.being.exception.being_exceptions import BeingSnapshotIncompleteException

        path = _capture_old_snapshot(tmp_path, {})
        self._make_legacy(path)
        dst = _make_environment()

        with pytest.raises(BeingSnapshotIncompleteException, match="no persona"):
            dst["restore"].execute(path)

        assert dst["repo"].find_snapshot_by_id(BeingId("being_w1_p1")) is None

    def test_current_snapshot_drops_no_identity(self, tmp_path: Path) -> None:
        """persona を持つ今のファイルでは、読み捨てた名前と一人称を返さない。"""
        path = _capture_old_snapshot(tmp_path, {})

        assert _make_environment()["restore"].execute(path).removed_legacy_identity is None
