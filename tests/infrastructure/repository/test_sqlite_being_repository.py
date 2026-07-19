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

    def test_save_find_id_being(
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

    def test_id_find_id_none(
        self, repo: SqliteBeingRepository
    ) -> None:
        """未保存の ID では None。"""
        assert repo.find_by_id(BeingId("missing")) is None

    def test_save_same_id_overwrites(self, repo: SqliteBeingRepository) -> None:
        """同 being_id で save し直すと内容が更新される (upsert)。"""
        repo.save(_being("ada", name="アダ"))
        repo.save(_being("ada", name="アダ2"))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.identity.name == "アダ2"

    def test_returns_exists_after_true(
        self, repo: SqliteBeingRepository
    ) -> None:
        """save 済みなら exists が True、未保存なら False。"""
        repo.save(_being("ada"))
        assert repo.exists(BeingId("ada")) is True
        assert repo.exists(BeingId("missing")) is False

    def test_delete_true_false(
        self, repo: SqliteBeingRepository
    ) -> None:
        """存在する Being は delete で削除、未保存は False。"""
        repo.save(_being("ada"))
        assert repo.delete(BeingId("ada")) is True
        assert repo.find_by_id(BeingId("ada")) is None
        assert repo.delete(BeingId("missing")) is False


class TestSqliteBeingRepositoryAttachmentRoundtrip:
    """attachment の partial state を生じさせない永続化挙動。"""

    def test_attach_being_attachment_none_restored(
        self, repo: SqliteBeingRepository
    ) -> None:
        """attachment 未設定 Being は復元後も is_attached=False。"""
        repo.save(_being(attached=False))
        loaded = repo.find_by_id(BeingId("ada"))
        assert loaded is not None
        assert loaded.is_attached is False

    def test_attach_being_attachment_restored(
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

    def test_two_initializations_run_migration_once(
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

    def test_save_after_snapshot_json(
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
        # Phase 4 Step 4-1: codec が常に最新 (=2) を出すため、ここも 2 を期待する。
        # 後方互換 (v1 行の load) は別テストで担保。
        assert row["snapshot_version"] == 2
        data = json.loads(row["snapshot_json"])
        assert data["being_id_value"] == "ada"
        assert data["identity_name"] == "アダ"
        assert data["attachment_world_id"] == 1
        assert data["attachment_player_id"] == 2
        assert data["declared_memory_kinds"] == ["memo"]


class TestSqliteBeingRepositoryMemoryPayload:
    """Phase 4 Step 4-1: memory_payload_json の永続化 round-trip。"""

    def test_payload_dict_memory_payload_json_included(self) -> None:
        """_snapshot_to_payload_dict が v2 snapshot の payload を落とさない。"""
        from ai_rpg_world.domain.being.value_object.being_snapshot import (
            BeingSnapshot,
        )
        from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
            _payload_dict_to_snapshot,
            _snapshot_to_payload_dict,
        )

        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=1,
            attachment_player_id=2,
            declared_memory_kinds=("memo",),
            snapshot_version=2,
            memory_payload_json='{"memo": [{"id": "m1"}]}',
        )
        payload_dict = _snapshot_to_payload_dict(snapshot)
        assert payload_dict["memory_payload_json"] == '{"memo": [{"id": "m1"}]}'

        # JSON シリアライズ → 復元の round-trip でも payload が保たれる。
        restored = _payload_dict_to_snapshot(json.loads(json.dumps(payload_dict)))
        assert restored == snapshot

    def test_v1_line_payload_none(self) -> None:
        """v1 schema の snapshot_json には memory_payload_json キーがない。"""
        from ai_rpg_world.infrastructure.repository.sqlite_being_repository import (
            _payload_dict_to_snapshot,
        )

        v1_data = {
            "being_id_value": "ada",
            "identity_name": "アダ",
            "identity_first_person": "わたし",
            "attachment_world_id": None,
            "attachment_player_id": None,
            "declared_memory_kinds": [],
            "snapshot_version": 1,
        }
        snapshot = _payload_dict_to_snapshot(v1_data)
        assert snapshot.memory_payload_json is None
        assert snapshot.snapshot_version == 1


class TestSqliteBeingRepositoryFindAllAttachedTo:
    """find_all_attached_to の挙動 (= Phase 3 Step 2 で追加、JSON1 経由クエリ)。"""

    def test_one_attached_being_matches_query(
        self, repo: SqliteBeingRepository
    ) -> None:
        """正常系: ある (world, player) に attach 中の Being を 1 件返す。"""
        repo.save(_being("ada", attached=True))
        result = repo.find_all_attached_to(WorldId(1), PlayerId(2))
        assert len(result) == 1
        assert result[0].being_id == BeingId("ada")
        assert result[0].is_attached is True

    def test_attach_being(
        self, repo: SqliteBeingRepository
    ) -> None:
        """attachment_world_id が NULL の行は WHERE で除外される。"""
        repo.save(_being("ada", attached=False))
        assert repo.find_all_attached_to(WorldId(1), PlayerId(2)) == []

    def test_returns_all_world_player_multiple_being(
        self, repo: SqliteBeingRepository
    ) -> None:
        """異常状態検出は Resolver の責務なので、ここは全件返す。"""
        repo.save(_being("ada", attached=True))
        # ben を同じ (world=1, player=2) に attach 済みで保存
        from ai_rpg_world.domain.being.aggregate.being import Being
        from ai_rpg_world.domain.being.value_object.being_attachment import (
            BeingAttachment,
        )

        ben = Being(
            being_id=BeingId("ben"),
            identity=BeingIdentity(name="ベン", first_person="俺"),
            attachment=BeingAttachment(
                world_id=WorldId(1), player_id=PlayerId(2)
            ),
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

    def test_save_being_raises_type_error(
        self, repo: SqliteBeingRepository
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.save("not-a-being")  # type: ignore[arg-type]

    def test_find_by_id_being_id_raises_type_error(
        self, repo: SqliteBeingRepository
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            repo.find_by_id("ada")  # type: ignore[arg-type]
