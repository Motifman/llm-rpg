"""Trade コマンド経路向けドメイン書き込みテーブル（`GAME_DB_PATH` 単一 DB に同居）。"""
from __future__ import annotations

import sqlite3


def init_game_write_schema(connection: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS` のみ。コミットは呼び出し側（UoW またはブートストラップ）。"""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_sequences (
            name TEXT PRIMARY KEY NOT NULL,
            next_value INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_aggregates (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            seller_id INTEGER NOT NULL,
            offered_item_id INTEGER NOT NULL,
            requested_gold INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            target_player_id INTEGER,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            buyer_id INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_profiles (
            player_id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            race TEXT NOT NULL,
            element TEXT NOT NULL,
            control_type TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_items (
            item_instance_id INTEGER PRIMARY KEY NOT NULL,
            item_spec_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_inventories (
            player_id INTEGER PRIMARY KEY NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_player_statuses (
            player_id INTEGER PRIMARY KEY NOT NULL,
            aggregate_blob BLOB NOT NULL
        )
        """
    )
    # シーケンス行は allocate_sequence_value 初回呼び出しで INSERT OR IGNORE する。
    # ここで INSERT すると sqlite3 の暗黙トランザクションが開いたまま残り、
    # 後続の明示 BEGIN と衝突するため行わない。


def allocate_sequence_value(connection: sqlite3.Connection, name: str) -> int:
    """同一接続・同一トランザクション内で採番する。rollback すると採番も巻き戻る。"""
    connection.execute(
        "INSERT OR IGNORE INTO game_sequences (name, next_value) VALUES (?, 0)",
        (name,),
    )
    connection.execute(
        "UPDATE game_sequences SET next_value = next_value + 1 WHERE name = ?",
        (name,),
    )
    cur = connection.execute(
        "SELECT next_value FROM game_sequences WHERE name = ?",
        (name,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"sequence missing after init: {name}")
    return int(row[0])


__all__ = ["allocate_sequence_value", "init_game_write_schema"]
