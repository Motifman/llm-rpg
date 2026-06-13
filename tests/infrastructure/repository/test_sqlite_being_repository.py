"""SqliteBeingRepository の永続化挙動。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
    SqliteBeingRepository,
)


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


def _being(
    being_id: str = "ada",
    name: str = "アダ",
    attached: bool = False,
    kinds: list[MemoryKind] | None = None,
) -> Being:
    attachment = (
        BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        if attached
        else None
    )
    return Being(
        being_id=BeingId(being_id),
        identity=BeingIdentity(name=name, first_person="わたし"),
        attachment=attachment,
        declared_memory_kinds=kinds or [],
    )


@pytest.fixture
def repo() -> SqliteBeingRepository:
    """各テスト用にインメモリ SQLite 接続から Repository を組む。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return SqliteBeingRepository(conn)


class TestSqliteBeingRepositoryCrud:
    """SqliteBeingRepository の CRUD 挙動。"""

    def test_save_して_find_by_id_で同等の_Being_が取り出せる(
        self, repo: SqliteBeingRepository
    ) -> None:
        """ラウンドトリップで identity / attachment / kinds が一致。"""
        original = _being(
            attached=True,
            kinds=[MemoryKind.EPISODIC, MemoryKind.MEMO],
        )
        repo.save(original)
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.being_id == original.being_id
        assert loaded.identity == original.identity
        assert loaded.attachment == original.attachment
        assert loaded.declared_memory_kinds == original.declared_memory_kinds

    def test_存在しない_ID_の_find_by_id_は_None(
        self, repo: SqliteBeingRepository
    ) -> None:
        """未保存の ID では None。"""
        assert repo.find_by_id(BeingId("missing")) is None

    def test_save_は同一_ID_を上書きする(self, repo: SqliteBeingRepository) -> None:
        """同 being_id で save し直すと内容が更新される (upsert)。"""
        repo.save(_being("ada", name="アダ"))
        repo.save(_being("ada", name="アダ2"))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.identity.name == "アダ2"

    def test_exists_は保存後_True_を返す(
        self, repo: SqliteBeingRepository
    ) -> None:
        """save 済みなら exists が True、未保存なら False。"""
        repo.save(_being("ada"))
        assert repo.exists(BeingId("ada")) is True
        assert repo.exists(BeingId("missing")) is False

    def test_delete_は存在すれば_True_で削除し_未保存なら_False(
        self, repo: SqliteBeingRepository
    ) -> None:
        """存在する Being は delete で削除、未保存は False。"""
        repo.save(_being("ada"))
        assert repo.delete(BeingId("ada")) is True
        assert repo.find_by_id(BeingId("ada")) is None
        assert repo.delete(BeingId("missing")) is False


class TestSqliteBeingRepositoryAttachmentRoundtrip:
    """attachment の partial state を生じさせない永続化挙動。"""

    def test_未_attach_の_Being_も_attachment_None_で復元される(
        self, repo: SqliteBeingRepository
    ) -> None:
        """attachment 未設定 Being は復元後も is_attached=False。"""
        repo.save(_being(attached=False))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.is_attached is False

    def test_attach_済み_Being_は_attachment_両フィールドで復元される(
        self, repo: SqliteBeingRepository
    ) -> None:
        """attached Being は復元後も world / player 両方が埋まる。"""
        repo.save(_being(attached=True))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.attachment is not None
        assert loaded.attachment.world_id == WorldId(1)
        assert loaded.attachment.player_id == PlayerId(2)


class TestSqliteBeingRepositorySchema:
    """SQLite schema / migration 挙動。"""

    def test_2回初期化しても_migration_は_1回だけ走る(
        self, tmp_path: Path
    ) -> None:
        """同じ DB ファイルに再接続しても migration は冪等。"""
        db_path = tmp_path / "beings.db"
        repo1 = SqliteBeingRepository.connect(str(db_path))
        repo1.save(_being("ada"))
        repo2 = SqliteBeingRepository.connect(str(db_path))
        loaded = repo2.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.identity.name == "アダ"

    def test_save_後の_snapshot_json_は_JSON_として読める(
        self, repo: SqliteBeingRepository
    ) -> None:
        """SQL を直接叩いて payload が想定形であることを確認。"""
        repo.save(_being(attached=True, kinds=[MemoryKind.MEMO]))
        cur = repo.connection.cursor()
        cur.execute(
            "SELECT snapshot_version, snapshot_json FROM beings WHERE being_id_value = ?",
            ("ada",),
        )
        row = cur.fetchone()
        assert row is not None
        assert row["snapshot_version"] == 1
        data = json.loads(row["snapshot_json"])
        assert data["being_id_value"] == "ada"
        assert data["identity_name"] == "アダ"
        assert data["attachment_world_id"] == 1
        assert data["attachment_player_id"] == 2
        assert data["declared_memory_kinds"] == ["memo"]


class TestSqliteBeingRepositoryTypeGuards:
    """型違反の弾き方。"""

    def test_save_に非_Being_を渡すと_TypeError(
        self, repo: SqliteBeingRepository
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.save("not-a-being")  # type: ignore[arg-type]

    def test_find_by_id_に非_BeingId_を渡すと_TypeError(
        self, repo: SqliteBeingRepository
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.find_by_id("ada")  # type: ignore[arg-type]
