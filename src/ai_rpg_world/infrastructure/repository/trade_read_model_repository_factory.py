"""Composition root 向け: Trade ReadModel リポジトリをパスまたは環境変数から生成する。

既定は `InMemoryTradeReadModelRepository`。`TRADE_READMODEL_DB_PATH` に SQLite ファイルパスを
設定すると `SqliteTradeReadModelRepository` を返す。

`TradeQueryService`・`TradePageQueryService`・`TradeEventHandler` には同一のリポジトリ
インスタンスを注入すること（ReadModel の投影とクエリの一貫性のため）。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)

_ENV_TRADE_READMODEL_DB_PATH = "TRADE_READMODEL_DB_PATH"


def create_trade_read_model_repository_from_path(
    db_path: Optional[Union[str, Path]],
) -> TradeReadModelRepository:
    """ファイルパスが与えられれば SQLite、空ならインメモリを返す。"""
    if db_path is None:
        return InMemoryTradeReadModelRepository()
    if isinstance(db_path, str) and not db_path.strip():
        return InMemoryTradeReadModelRepository()
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    return SqliteTradeReadModelRepository(conn)


def create_trade_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeReadModelRepository:
    """環境変数 `TRADE_READMODEL_DB_PATH` に基づきリポジトリを生成する。

    未設定・空文字のときはインメモリ。テストでは `environ` に差し替え可能。
    """
    env = environ if environ is not None else os.environ
    raw = env.get(_ENV_TRADE_READMODEL_DB_PATH, "") or ""
    raw = raw.strip()
    if not raw:
        return InMemoryTradeReadModelRepository()
    return create_trade_read_model_repository_from_path(raw)


__all__ = [
    "create_trade_read_model_repository_from_env",
    "create_trade_read_model_repository_from_path",
]
