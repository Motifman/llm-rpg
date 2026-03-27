"""`GAME_DB_PATH` に基づき GlobalMarketListingReadModel リポジトリを生成する。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.domain.trade.repository.global_market_listing_read_model_repository import (
    GlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.game_db_path import (
    ensure_parent_dir,
    get_game_db_path_from_env,
)
from ai_rpg_world.infrastructure.repository.in_memory_global_market_listing_read_model_repository import (
    InMemoryGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_global_market_listing_read_model_repository import (
    SqliteGlobalMarketListingReadModelRepository,
)


def create_global_market_listing_read_model_repository_from_path(
    db_path: Optional[Union[str, Path]],
) -> GlobalMarketListingReadModelRepository:
    if db_path is None:
        return InMemoryGlobalMarketListingReadModelRepository()
    if isinstance(db_path, str) and not db_path.strip():
        return InMemoryGlobalMarketListingReadModelRepository()
    path = str(Path(db_path).expanduser().resolve())
    ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    return SqliteGlobalMarketListingReadModelRepository.for_standalone_connection(conn)


def create_global_market_listing_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> GlobalMarketListingReadModelRepository:
    resolved = get_game_db_path_from_env(environ=environ if environ is not None else os.environ)
    if resolved is None:
        return InMemoryGlobalMarketListingReadModelRepository()
    return create_global_market_listing_read_model_repository_from_path(resolved)


__all__ = [
    "create_global_market_listing_read_model_repository_from_env",
    "create_global_market_listing_read_model_repository_from_path",
]
