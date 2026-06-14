"""MemoryLink / セマンティック記憶用 SQLite スキーマ（主観エピソード DB と同一ファイルに同居）。"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

_MEMORY_GRAPH_SCHEMA_NAMESPACE = "episodic-memory-graph-v1"


def _init_memory_graph_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE memory_links (
            link_id TEXT PRIMARY KEY NOT NULL,
            player_id INTEGER NOT NULL,
            episode_id_a TEXT NOT NULL,
            episode_id_b TEXT NOT NULL,
            link_type TEXT NOT NULL,
            strength REAL NOT NULL,
            co_activation_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_activated_at TEXT NOT NULL,
            decay_rate REAL NOT NULL,
            UNIQUE (player_id, episode_id_a, episode_id_b, link_type)
        );
        CREATE INDEX idx_memory_links_player ON memory_links (player_id);
        CREATE INDEX idx_memory_links_player_a ON memory_links (player_id, episode_id_a);
        CREATE INDEX idx_memory_links_player_b ON memory_links (player_id, episode_id_b);

        CREATE TABLE semantic_memory_entries (
            entry_id TEXT PRIMARY KEY NOT NULL,
            player_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            evidence_episode_ids_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_semantic_entries_player
            ON semantic_memory_entries (player_id, created_at DESC);

        CREATE TABLE semantic_cluster_signatures (
            player_id INTEGER NOT NULL,
            evidence_signature TEXT NOT NULL,
            PRIMARY KEY (player_id, evidence_signature)
        );
        """
    )


def _init_memory_graph_v2_semantic_by_being(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3b-1: being_id keyed の semantic 並走テーブルを追加。

    legacy ``semantic_memory_entries`` / ``semantic_cluster_signatures`` はそのまま
    残し、新 API は本 v2 テーブルに書き込む (= caller 移行 = Step 3b-2 後、
    Step 3b-3 で legacy テーブルごと撤去する想定)。
    """
    connection.executescript(
        """
        CREATE TABLE semantic_memory_entries_by_being (
            entry_id TEXT NOT NULL,
            being_id_value TEXT NOT NULL,
            text TEXT NOT NULL,
            evidence_episode_ids_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            importance_score INTEGER NOT NULL DEFAULT 5,
            tags_json TEXT NOT NULL DEFAULT '[]',
            player_id INTEGER NOT NULL,
            PRIMARY KEY (being_id_value, entry_id)
        );
        CREATE INDEX idx_semantic_entries_by_being
            ON semantic_memory_entries_by_being (being_id_value, created_at DESC);

        CREATE TABLE semantic_cluster_signatures_by_being (
            being_id_value TEXT NOT NULL,
            evidence_signature TEXT NOT NULL,
            PRIMARY KEY (being_id_value, evidence_signature)
        );
        """
    )


def _init_memory_graph_v3_drop_legacy_semantic(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3b-3: legacy player_id keyed の semantic テーブルを撤去。

    Step 3b-2 で全 caller が ``*_by_being`` API に切り替わったため、player_id keyed
    の旧テーブル/インデックスは参照されなくなった。schema migration で DROP して
    DB ファイル上にも残らないようにする。

    ``memory_links`` テーブル (= MemoryLinkRepository 用) は本 v3 では触らない。
    そちらの being_id keyed 移行は後続 Step 3c で行う。
    """
    connection.executescript(
        """
        DROP INDEX IF EXISTS idx_semantic_entries_player;
        DROP TABLE IF EXISTS semantic_memory_entries;
        DROP TABLE IF EXISTS semantic_cluster_signatures;
        """
    )


def _init_memory_graph_v4_memory_link_by_being(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3c-1: being_id keyed の memory_link 並走テーブルを追加。

    legacy ``memory_links`` はそのまま残し、新 API は本 v4 テーブルに書き込む
    (= caller 移行 = Step 3c-2 後、Step 3c-3 で legacy テーブルごと撤去する想定)。
    semantic の v2/v3 と同じパターン。

    PK は (being_id_value, episode_id_a, episode_id_b, link_type)。``link_id`` は
    存在するが PK ではない (legacy 同様、UPSERT 時に更新可能フィールド扱い)。
    """
    connection.executescript(
        """
        CREATE TABLE memory_links_by_being (
            link_id TEXT NOT NULL,
            being_id_value TEXT NOT NULL,
            episode_id_a TEXT NOT NULL,
            episode_id_b TEXT NOT NULL,
            link_type TEXT NOT NULL,
            strength REAL NOT NULL,
            co_activation_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_activated_at TEXT NOT NULL,
            decay_rate REAL NOT NULL,
            player_id INTEGER NOT NULL,
            PRIMARY KEY (being_id_value, episode_id_a, episode_id_b, link_type)
        );
        CREATE INDEX idx_memory_links_by_being
            ON memory_links_by_being (being_id_value);
        CREATE INDEX idx_memory_links_by_being_a
            ON memory_links_by_being (being_id_value, episode_id_a);
        CREATE INDEX idx_memory_links_by_being_b
            ON memory_links_by_being (being_id_value, episode_id_b);
        """
    )


def apply_memory_graph_migrations(connection: sqlite3.Connection) -> int:
    """リンク・セマンティック表を同一 DB に作成する。namespace はエピソード本体と独立。"""
    return apply_migrations(
        connection,
        namespace=_MEMORY_GRAPH_SCHEMA_NAMESPACE,
        migrations=[
            SqliteMigration(1, _init_memory_graph_v1),
            SqliteMigration(2, _init_memory_graph_v2_semantic_by_being),
            SqliteMigration(3, _init_memory_graph_v3_drop_legacy_semantic),
            SqliteMigration(4, _init_memory_graph_v4_memory_link_by_being),
        ],
    )


__all__ = ["apply_memory_graph_migrations"]
