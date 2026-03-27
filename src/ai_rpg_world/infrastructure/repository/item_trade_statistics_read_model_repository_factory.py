"""`GAME_DB_PATH` に基づき ItemTradeStatisticsReadModel リポジトリを生成する。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.domain.trade.repository.item_trade_statistics_read_model_repository import (
    ItemTradeStatisticsReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.game_db_path import (
    ensure_parent_dir,
    get_game_db_path_from_env,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_trade_statistics_read_model_repository import (
    InMemoryItemTradeStatisticsReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_trade_statistics_read_model_repository import (
    SqliteItemTradeStatisticsReadModelRepository,
)


def create_item_trade_statistics_read_model_repository_from_path(
    db_path: Optional[Union[str, Path]],
) -> ItemTradeStatisticsReadModelRepository:
    if db_path is None:
        return InMemoryItemTradeStatisticsReadModelRepository()
    if isinstance(db_path, str) and not db_path.strip():
        return InMemoryItemTradeStatisticsReadModelRepository()
    path = str(Path(db_path).expanduser().resolve())
    ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    return SqliteItemTradeStatisticsReadModelRepository.for_standalone_connection(conn)


def create_item_trade_statistics_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> ItemTradeStatisticsReadModelRepository:
    resolved = get_game_db_path_from_env(environ=environ if environ is not None else os.environ)
    if resolved is None:
        return InMemoryItemTradeStatisticsReadModelRepository()
    return create_item_trade_statistics_read_model_repository_from_path(resolved)


__all__ = [
    "create_item_trade_statistics_read_model_repository_from_env",
    "create_item_trade_statistics_read_model_repository_from_path",
]
