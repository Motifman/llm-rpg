"""`GAME_DB_PATH` に基づき PersonalTradeListingReadModel リポジトリを生成する。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.domain.trade.repository.personal_trade_listing_read_model_repository import (
    PersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.game_db_path import (
    ensure_parent_dir,
    get_game_db_path_from_env,
)
from ai_rpg_world.infrastructure.repository.in_memory_personal_trade_listing_read_model_repository import (
    InMemoryPersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_personal_trade_listing_read_model_repository import (
    SqlitePersonalTradeListingReadModelRepository,
)


def create_personal_trade_listing_read_model_repository_from_path(
    db_path: Optional[Union[str, Path]],
) -> PersonalTradeListingReadModelRepository:
    """パスがあれば SQLite、空ならインメモリ。"""
    if db_path is None:
        return InMemoryPersonalTradeListingReadModelRepository()
    if isinstance(db_path, str) and not db_path.strip():
        return InMemoryPersonalTradeListingReadModelRepository()
    path = str(Path(db_path).expanduser().resolve())
    ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    return SqlitePersonalTradeListingReadModelRepository(conn)


def create_personal_trade_listing_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> PersonalTradeListingReadModelRepository:
    """環境変数 `GAME_DB_PATH` に基づきリポジトリを返す。"""
    resolved = get_game_db_path_from_env(environ=environ if environ is not None else os.environ)
    if resolved is None:
        return InMemoryPersonalTradeListingReadModelRepository()
    return create_personal_trade_listing_read_model_repository_from_path(resolved)


__all__ = [
    "create_personal_trade_listing_read_model_repository_from_env",
    "create_personal_trade_listing_read_model_repository_from_path",
]
