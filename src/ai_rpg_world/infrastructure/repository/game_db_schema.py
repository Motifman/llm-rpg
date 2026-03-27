"""Unified bootstrap for the single game SQLite database."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.global_market_listing_read_model_sqlite import (
    init_global_market_listing_read_model_schema,
)
from ai_rpg_world.infrastructure.repository.personal_trade_listing_read_model_sqlite import (
    init_personal_trade_listing_read_model_schema,
)
from ai_rpg_world.infrastructure.repository.trade_detail_read_model_sqlite import (
    init_trade_detail_read_model_schema,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_sqlite import (
    init_trade_read_model_schema,
)


def init_game_db_schema(connection: sqlite3.Connection) -> None:
    """Materialize every schema that currently belongs to the single game DB."""
    if connection.row_factory is not sqlite3.Row:
        connection.row_factory = sqlite3.Row
    init_game_write_schema(connection)
    init_trade_read_model_schema(connection)
    init_trade_detail_read_model_schema(connection)
    init_personal_trade_listing_read_model_schema(connection)
    init_global_market_listing_read_model_schema(connection)


__all__ = ["init_game_db_schema"]
