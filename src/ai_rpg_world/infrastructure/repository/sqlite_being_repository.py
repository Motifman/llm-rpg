"""SqliteBeingRepository — Being 集約の SQLite 永続化実装。

Issue #470 Phase 3 Step 1: Phase 2 PR4 で完成した BeingSnapshot / Codec を
シリアライズ形式として使い、Being 集約を SQLite に永続化する。

## Schema

```
CREATE TABLE beings (
    being_id_value TEXT PRIMARY KEY NOT NULL,
    snapshot_version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- ``being_id_value`` を PK にした単純な KV ストア
- ``snapshot_json`` は ``BeingSnapshot`` を JSON シリアライズしたもの (= codec が
  encode した primitive 構造をそのままダンプ)
- ``snapshot_version`` を別カラムに切ることで、将来 ``SUPPORTED_VERSIONS`` で
  filter したクエリ (= 旧版 snapshot だけ migrate する用途等) を SQL レベルで
  書ける

## Phase 3 Step 1 のスコープ

- Being 集約 root の永続化のみ (= memory store 中身は含まない)
- memory store と Being の接続は Step 3 で 1 store ずつ移行
- run 間で Being identity (= name / first_person / attachment / declared_kinds)
  が確実に残ることをここで担保する
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

_BEING_SCHEMA_NAMESPACE = "beings-v1"

# 旧 DB 行が ``snapshot_version`` 列を持たない場合のフォールバック。
# 「列が欠落 = 最古世代」の意味論なので CURRENT_SNAPSHOT_VERSION ではなく
# 1 で固定する (= 将来 CURRENT が 2 以上に上がっても旧データは v1 として扱う)。
_FALLBACK_SNAPSHOT_VERSION = 1


def _init_schema_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE beings (
            being_id_value TEXT PRIMARY KEY NOT NULL,
            snapshot_version INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _snapshot_to_payload_dict(snapshot: BeingSnapshot) -> dict[str, Any]:
    """BeingSnapshot を JSON 互換 dict に変換する。

    primitive のみで構成されているので素直にダンプできる。
    """
    return {
        "being_id_value": snapshot.being_id_value,
        "identity_name": snapshot.identity_name,
        "identity_first_person": snapshot.identity_first_person,
        "attachment_world_id": snapshot.attachment_world_id,
        "attachment_player_id": snapshot.attachment_player_id,
        "declared_memory_kinds": list(snapshot.declared_memory_kinds),
        "snapshot_version": snapshot.snapshot_version,
    }


def _payload_dict_to_snapshot(data: dict[str, Any]) -> BeingSnapshot:
    """JSON 由来 dict から BeingSnapshot を再構築する。

    BeingSnapshot.__post_init__ の構造検証はそのまま走る (= all-or-nothing
    の門で再度ガードされる)。
    """
    raw_kinds = data.get("declared_memory_kinds", [])
    if not isinstance(raw_kinds, list):
        raise ValueError(
            f"declared_memory_kinds must be JSON array, got {type(raw_kinds).__name__}"
        )
    return BeingSnapshot(
        being_id_value=data["being_id_value"],
        identity_name=data["identity_name"],
        identity_first_person=data["identity_first_person"],
        attachment_world_id=data.get("attachment_world_id"),
        attachment_player_id=data.get("attachment_player_id"),
        declared_memory_kinds=tuple(raw_kinds),
        snapshot_version=data.get("snapshot_version", _FALLBACK_SNAPSHOT_VERSION),
    )


class SqliteBeingRepository(BeingRepository):
    """Being 集約を SQLite に保存する Repository 実装。"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_migrations(
            connection,
            namespace=_BEING_SCHEMA_NAMESPACE,
            migrations=[SqliteMigration(1, _init_schema_v1)],
        )
        self._smoke_check_json1()

    def _smoke_check_json1(self) -> None:
        """SQLite JSON1 拡張が使えるかを起動時に確認する。

        ``find_all_attached_to`` が ``json_extract`` に依存するため、JSON1 拡張
        が無効な環境 (古い SQLite / 特殊ビルド) では fail-fast で落としたい。
        SQLite 3.38+ では既定有効だが、Alpine Linux や古い CI イメージ等で
        欠落するケースに備える。
        """
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT json_extract('{\"a\":1}', '$.a')")
            cur.fetchone()
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                "SqliteBeingRepository requires SQLite JSON1 extension "
                "(json_extract) but it appears unavailable. "
                "Use SQLite 3.38+ or a build with SQLITE_ENABLE_JSON1."
            ) from e

    @property
    def connection(self) -> sqlite3.Connection:
        """同一 DB ファイルに同居する他 store と接続を共有するためのアクセサ。"""
        return self._conn

    @classmethod
    def connect(cls, database_path: str) -> "SqliteBeingRepository":
        """SQLite ファイルパスから Repository を組み立てるファクトリ。

        ``apply_migrations`` が必要な ``commit`` を内部で済ませるため、
        本ファクトリ側では追加の commit を打たない (= 冗長 commit を排除し、
        将来同一接続を他 store と共有した際の挙動を予測可能に保つ)。
        """
        conn = sqlite3.connect(database_path, check_same_thread=False)
        return cls(conn)

    def save(self, being: Being) -> None:
        if not isinstance(being, Being):
            raise TypeError(f"being must be Being, got {type(being).__name__}")

        snapshot = BeingSnapshotCodec.encode(being)
        payload = json.dumps(
            _snapshot_to_payload_dict(snapshot), ensure_ascii=False
        )
        updated_at = datetime.now(timezone.utc).isoformat()

        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO beings (being_id_value, snapshot_version, snapshot_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(being_id_value) DO UPDATE SET
                snapshot_version = excluded.snapshot_version,
                snapshot_json = excluded.snapshot_json,
                updated_at = excluded.updated_at
            """,
            (
                snapshot.being_id_value,
                snapshot.snapshot_version,
                payload,
                updated_at,
            ),
        )
        self._conn.commit()

    def find_by_id(self, being_id: BeingId) -> Being | None:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )

        cur = self._conn.cursor()
        cur.execute(
            "SELECT snapshot_json FROM beings WHERE being_id_value = ?",
            (being_id.value,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        data = json.loads(row["snapshot_json"])
        snapshot = _payload_dict_to_snapshot(data)
        return BeingSnapshotCodec.decode(snapshot)

    def exists(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        cur = self._conn.cursor()
        cur.execute(
            "SELECT 1 FROM beings WHERE being_id_value = ? LIMIT 1",
            (being_id.value,),
        )
        return cur.fetchone() is not None

    def delete(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM beings WHERE being_id_value = ?",
            (being_id.value,),
        )
        deleted = cur.rowcount > 0
        self._conn.commit()
        return deleted

    def find_all_attached_to(
        self, world_id: WorldId, player_id: PlayerId
    ) -> list[Being]:
        """JSON カラム経由で attach 検索する。

        SQLite JSON1 拡張の ``json_extract`` で attachment フィールドを直接
        WHERE 句に指定する。インデックスは貼っていないので全行 scan だが、
        Beings は 1 run につき数件程度の想定で許容範囲。将来規模が増えたら
        専用カラム (= attachment_world_id / attachment_player_id) を v2
        migration で追加して indexed query に差し替える出口を残す。
        """
        if not isinstance(world_id, WorldId):
            raise TypeError(
                f"world_id must be WorldId, got {type(world_id).__name__}"
            )
        if not isinstance(player_id, PlayerId):
            raise TypeError(
                f"player_id must be PlayerId, got {type(player_id).__name__}"
            )

        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT snapshot_json FROM beings
            WHERE json_extract(snapshot_json, '$.attachment_world_id') = ?
              AND json_extract(snapshot_json, '$.attachment_player_id') = ?
            """,
            (world_id.value, player_id.value),
        )
        result: list[Being] = []
        for row in cur.fetchall():
            data = json.loads(row["snapshot_json"])
            snapshot = _payload_dict_to_snapshot(data)
            result.append(BeingSnapshotCodec.decode(snapshot))
        return result


__all__ = ["SqliteBeingRepository"]
