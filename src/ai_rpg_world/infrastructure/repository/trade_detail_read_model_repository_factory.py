"""`GAME_DB_PATH` に基づき TradeDetailReadModel リポジトリを生成する。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.domain.trade.repository.trade_detail_read_model_repository import (
    TradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.game_db_path import (
    ensure_parent_dir,
    get_game_db_path_from_env,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_detail_read_model_repository import (
    InMemoryTradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_detail_read_model_repository import (
    SqliteTradeDetailReadModelRepository,
)


def create_trade_detail_read_model_repository_from_path(
    db_path: Optional[Union[str, Path]],
) -> TradeDetailReadModelRepository:
    if db_path is None:
        return InMemoryTradeDetailReadModelRepository()
    if isinstance(db_path, str) and not db_path.strip():
        return InMemoryTradeDetailReadModelRepository()
    path = str(Path(db_path).expanduser().resolve())
    ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    return SqliteTradeDetailReadModelRepository.for_standalone_connection(conn)


def create_trade_detail_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeDetailReadModelRepository:
    resolved = get_game_db_path_from_env(environ=environ if environ is not None else os.environ)
    if resolved is None:
        return InMemoryTradeDetailReadModelRepository()
    return create_trade_detail_read_model_repository_from_path(resolved)


__all__ = [
    "create_trade_detail_read_model_repository_from_env",
    "create_trade_detail_read_model_repository_from_path",
]
