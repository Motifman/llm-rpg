"""SqliteBeingRepository の永続化挙動。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import BeingSnapshotIncompleteException
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
    SqliteBeingRepository,
)


def _being(
    being_id: str = "ada",
    name: str = "アダ",
    attached: bool = False,
) -> Being:
    attachment = BeingAttachment(world_id=1, player_id=2) if attached else None
    return Being(
        being_id=BeingId(being_id),
        persona=Persona(name=name, first_person="わたし", traits=("慎重",)),
        attachment=attachment,
    )


@pytest.fixture
def repo() -> SqliteBeingRepository:
    """各テスト用にインメモリ SQLite 接続から Repository を組む。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return SqliteBeingRepository(conn)


class TestSqliteBeingRepositoryCrud:
    """SqliteBeingRepository の CRUD 挙動。"""

    def test_save_find_id_being(self, repo: SqliteBeingRepository) -> None:
        """保存して読み直すと、人柄と所属が一致する。"""
        original = _being(attached=True)
        repo.save(original)
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.being_id == original.being_id
        assert loaded.persona == original.persona
        assert loaded.attachment == original.attachment

    def test_id_find_id_none(self, repo: SqliteBeingRepository) -> None:
        """未保存の ID では None。"""
        assert repo.find_by_id(BeingId("missing")) is None

    def test_save_same_id_overwrites(self, repo: SqliteBeingRepository) -> None:
        """同 being_id で save し直すと内容が更新される (upsert)。"""
        repo.save(_being("ada", name="アダ"))
        repo.save(_being("ada", name="アダ2"))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.persona.name == "アダ2"

    def test_returns_exists_after_true(self, repo: SqliteBeingRepository) -> None:
        """save 済みなら exists が True、未保存なら False。"""
        repo.save(_being("ada"))
        assert repo.exists(BeingId("ada")) is True
        assert repo.exists(BeingId("missing")) is False

    def test_delete_true_false(self, repo: SqliteBeingRepository) -> None:
        """存在する Being は delete で削除、未保存は False。"""
        repo.save(_being("ada"))
        assert repo.delete(BeingId("ada")) is True
        assert repo.find_by_id(BeingId("ada")) is None
        assert repo.delete(BeingId("missing")) is False


class TestSqliteBeingRepositoryAttachmentRoundtrip:
    """attachment の partial state を生じさせない永続化挙動。"""

    def test_attach_being_attachment_none_restored(self, repo: SqliteBeingRepository) -> None:
        """attachment 未設定 Being は復元後も is_attached=False。"""
        repo.save(_being(attached=False))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.is_attached is False

    def test_attach_being_attachment_restored(self, repo: SqliteBeingRepository) -> None:
        """attached Being は復元後も world / player 両方が埋まる。"""
        repo.save(_being(attached=True))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.attachment is not None
        assert loaded.attachment.world_id == 1
        assert loaded.attachment.player_id == 2


class TestSqliteBeingRepositorySchema:
    """SQLite schema / migration 挙動。"""

    def test_two_initializations_run_migration_once(self, tmp_path: Path) -> None:
        """同じ DB ファイルに再接続しても migration は冪等。"""
        db_path = tmp_path / "beings.db"
        repo1 = SqliteBeingRepository.connect(str(db_path))
        repo1.save(_being("ada"))
        repo2 = SqliteBeingRepository.connect(str(db_path))
        loaded = repo2.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.persona.name == "アダ"

    def test_save_after_snapshot_json(self, repo: SqliteBeingRepository) -> None:
        """SQL を直接叩いて payload が想定形であることを確認。"""
        repo.save(_being(attached=True))
        cur = repo.connection.cursor()
        cur.execute(
            "SELECT snapshot_version, snapshot_json FROM beings WHERE being_id_value = ?",
            ("ada",),
        )
        row = cur.fetchone()
        assert row is not None
        # Phase 4 Step 4-1: codec が常に最新 (=2) を出すため、ここも 2 を期待する。
        # 後方互換 (v1 行の load) は別テストで担保。
        assert row["snapshot_version"] == 2
        data = json.loads(row["snapshot_json"])
        assert data["being_id_value"] == "ada"
        assert data["persona"]["name"] == "アダ"
        assert data["attachment_world_id"] == 1
        assert data["attachment_player_id"] == 2
        assert "declared_memory_kinds" not in data


class TestSqliteBeingRepositoryMemoryPayload:
    """memory_payload_json の永続化を保証する。"""

    def test_memory_payload_survives_save_and_find(self, repo: SqliteBeingRepository) -> None:
        """payload を載せた snapshot を保存して読み直すと、payload を含めて同じ snapshot が返る。"""
        from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot

        snapshot = BeingSnapshot(
            being_id_value="ada",
            persona=Persona(name="アダ", first_person="わたし"),
            attachment_world_id=1,
            attachment_player_id=2,
            snapshot_version=2,
            memory_payload_json='{"memo": [{"id": "m1"}]}',
        )

        repo.save_snapshot(snapshot)

        assert repo.find_snapshot_by_id(BeingId("ada")) == snapshot


class TestSqliteBeingRepositoryFindAllAttachedTo:
    """find_all_attached_to の挙動 (= Phase 3 Step 2 で追加、JSON1 経由クエリ)。"""

    def test_one_attached_being_matches_query(self, repo: SqliteBeingRepository) -> None:
        """正常系: ある (world, player) に attach 中の Being を 1 件返す。"""
        repo.save(_being("ada", attached=True))
        result = repo.find_all_attached_to(WorldId(1), PlayerId(2))
        assert len(result) == 1
        assert result[0].being_id == BeingId("ada")
        assert result[0].is_attached is True

    def test_attach_being(self, repo: SqliteBeingRepository) -> None:
        """attachment_world_id が NULL の行は WHERE で除外される。"""
        repo.save(_being("ada", attached=False))
        assert repo.find_all_attached_to(WorldId(1), PlayerId(2)) == []

    def test_returns_all_world_player_multiple_being(self, repo: SqliteBeingRepository) -> None:
        """異常状態検出は Resolver の責務なので、ここは全件返す。"""
        repo.save(_being("ada", attached=True))
        # ben を同じ (world=1, player=2) に attach 済みで保存
        from ai_rpg_world.being.domain.being import Being
        from ai_rpg_world.being.domain.being_attachment import (
            BeingAttachment,
        )

        ben = Being(
            being_id=BeingId("ben"),
            persona=Persona(name="ベン", first_person="俺"),
            attachment=BeingAttachment(world_id=1, player_id=2),
        )
        repo.save(ben)
        result = repo.find_all_attached_to(WorldId(1), PlayerId(2))
        assert {b.being_id.value for b in result} == {"ada", "ben"}

    def test_vo_raises_type_error(self, repo: SqliteBeingRepository) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="world_id"):
            repo.find_all_attached_to(1, PlayerId(2))  # type: ignore[arg-type]


class TestSqliteBeingRepositoryTypeGuards:
    """型違反の弾き方。"""

    def test_save_being_raises_type_error(self, repo: SqliteBeingRepository) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.save("not-a-being")  # type: ignore[arg-type]

    def test_find_by_id_being_id_raises_type_error(self, repo: SqliteBeingRepository) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.find_by_id("ada")  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [1, 2])
def test_old_database_row_without_persona_is_not_turned_into_a_being(tmp_path: Path, version: int) -> None:
    """persona の無い古い行は、名前と一人称を読み捨てる値として持つ snapshot として読み、人柄で埋めるまで Being にしない。"""
    database = tmp_path / "old.db"
    repo = SqliteBeingRepository.connect(str(database))
    original = _being(attached=True)
    repo.save(original)
    row = repo.connection.execute("SELECT snapshot_json FROM beings").fetchone()
    payload = json.loads(row[0])
    del payload["persona"]
    payload.update(identity_name="agent_2", identity_first_person="わたし", declared_memory_kinds=["semantic", "memo"])
    payload["snapshot_version"] = version
    repo.connection.execute(
        "UPDATE beings SET snapshot_version = ?, snapshot_json = ?",
        (version, json.dumps(payload)),
    )
    repo.connection.commit()
    repo.connection.close()

    reopened = SqliteBeingRepository.connect(str(database))
    try:
        snapshot = reopened.find_snapshot_by_id(original.being_id)
        assert snapshot.persona is None
        assert (snapshot.legacy_identity_name, snapshot.legacy_identity_first_person) == ("agent_2", "わたし")
        assert snapshot.legacy_declared_memory_kinds == ("semantic", "memo")
        with pytest.raises(BeingSnapshotIncompleteException, match="persona"):
            reopened.find_by_id(original.being_id)
    finally:
        reopened.connection.close()
