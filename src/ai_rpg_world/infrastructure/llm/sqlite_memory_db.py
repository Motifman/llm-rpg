"""LLM 記憶用 SQLite データベースのスキーマ管理"""

import sqlite3
from pathlib import Path
from typing import Optional, Union


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """指定パスの SQLite 接続を返す。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """
    LLM 記憶用テーブルを初期化する。
    episode_memories, episode_memory_entities, episode_memory_world_objects,
    episode_memory_scope_keys, long_term_facts, memory_laws, reflection_state
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episode_memories (
            id TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            context_summary TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            outcome_summary TEXT NOT NULL,
            location_id TEXT,
            timestamp TEXT NOT NULL,
            importance TEXT NOT NULL,
            surprise INTEGER NOT NULL,
            recall_count INTEGER NOT NULL DEFAULT 0,
            spot_id_value INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_episode_memories_player_timestamp
            ON episode_memories(player_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_episode_memories_player
            ON episode_memories(player_id);

        CREATE TABLE IF NOT EXISTS episode_memory_entities (
            episode_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (episode_id, entity_id),
            FOREIGN KEY (episode_id) REFERENCES episode_memories(id)
        );

        CREATE TABLE IF NOT EXISTS episode_memory_world_objects (
            episode_id TEXT NOT NULL,
            world_object_id INTEGER NOT NULL,
            PRIMARY KEY (episode_id, world_object_id),
            FOREIGN KEY (episode_id) REFERENCES episode_memories(id)
        );

        CREATE TABLE IF NOT EXISTS episode_memory_scope_keys (
            episode_id TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            PRIMARY KEY (episode_id, scope_key),
            FOREIGN KEY (episode_id) REFERENCES episode_memories(id)
        );
        CREATE INDEX IF NOT EXISTS idx_episode_scope_keys_scope
            ON episode_memory_scope_keys(scope_key);

        CREATE TABLE IF NOT EXISTS long_term_facts (
            id TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_long_term_facts_player
            ON long_term_facts(player_id);

        CREATE TABLE IF NOT EXISTS memory_laws (
            id TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            relation TEXT NOT NULL,
            target TEXT NOT NULL,
            strength REAL NOT NULL,
            UNIQUE(player_id, subject, relation, target)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_laws_player
            ON memory_laws(player_id);

        CREATE TABLE IF NOT EXISTS reflection_state (
            player_id INTEGER PRIMARY KEY,
            last_game_day INTEGER NOT NULL,
            last_cursor TEXT NOT NULL
        );
    """)
    conn.commit()
