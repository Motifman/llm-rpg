"""Trade コマンド向け SQLite 書き込みリポジトリ束（`GAME_DB_PATH` 単一 DB 想定）。"""
from __future__ import annotations

import sqlite3
from typing import Any, Tuple

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import SqliteItemWriteRepository
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import (
    SqliteTradeAggregateRepository,
)


def bootstrap_game_write_schema(connection: sqlite3.Connection) -> None:
    """DDL のみ。単一 game DB に載る既存スキーマをまとめて初期化する。"""
    init_game_db_schema(connection)


def attach_trade_command_sqlite_repositories(
    connection: sqlite3.Connection,
    *,
    event_sink: Any = None,
) -> Tuple[
    SqliteTradeAggregateRepository,
    SqlitePlayerInventoryWriteRepository,
    SqlitePlayerStatusWriteRepository,
    SqlitePlayerProfileWriteRepository,
    SqliteItemWriteRepository,
]:
    """同一接続・UoW 共有モードの 5 リポジトリ。`event_sink` に `TransactionalScope` を渡すと集約イベントを収集する。"""
    return (
        SqliteTradeAggregateRepository.for_shared_unit_of_work(
            connection, event_sink=event_sink
        ),
        SqlitePlayerInventoryWriteRepository.for_shared_unit_of_work(
            connection, event_sink=event_sink
        ),
        SqlitePlayerStatusWriteRepository.for_shared_unit_of_work(
            connection, event_sink=event_sink
        ),
        SqlitePlayerProfileWriteRepository.for_shared_unit_of_work(
            connection, event_sink=event_sink
        ),
        SqliteItemWriteRepository.for_shared_unit_of_work(connection, event_sink=event_sink),
    )


__all__ = [
    "attach_trade_command_sqlite_repositories",
    "bootstrap_game_write_schema",
]
