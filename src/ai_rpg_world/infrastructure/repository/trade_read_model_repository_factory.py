"""Composition root 向け: Trade ReadModel リポジトリをパスまたは環境変数から生成する。

既定は `InMemoryTradeReadModelRepository`。永続化パスは次の優先順位で解決する:

1. `TRADE_READMODEL_DB_PATH` が非空 → そのパス（従来どおり・明示上書き）
2. 上記が空で `GAME_DB_PATH` が非空 → 単一ゲーム DB（Phase 3–4 の方針）
3. どちらも空 → インメモリ

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
from ai_rpg_world.infrastructure.repository.game_db_path import get_game_db_path_from_env
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)

_ENV_TRADE_READMODEL_DB_PATH = "TRADE_READMODEL_DB_PATH"


def resolve_trade_read_model_persisted_path(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Trade メイン ReadModel 用の SQLite ファイルパス。無ければ None（インメモリ）。"""
    env = environ if environ is not None else os.environ
    raw_trade = (env.get(_ENV_TRADE_READMODEL_DB_PATH, "") or "").strip()
    if raw_trade:
        return str(Path(raw_trade).expanduser().resolve())
    return get_game_db_path_from_env(environ=env)


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
    return SqliteTradeReadModelRepository.for_standalone_connection(conn)


def attach_trade_read_model_repository_to_shared_connection(
    connection: sqlite3.Connection,
) -> SqliteTradeReadModelRepository:
    """既存の sqlite3 接続（例: `SqliteUnitOfWork.connection`）に ReadModel を載せる。

    書き込みの確定は接続を管理する UoW の `commit` に任せる。
    """
    return SqliteTradeReadModelRepository.for_shared_unit_of_work(connection)


def create_trade_read_model_repository_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeReadModelRepository:
    """`TRADE_READMODEL_DB_PATH` を優先し、無ければ `GAME_DB_PATH` で SQLite を選ぶ。

    どちらも空のときはインメモリ。テストでは `environ` に差し替え可能。
    """
    path = resolve_trade_read_model_persisted_path(environ=environ)
    if path is None:
        return InMemoryTradeReadModelRepository()
    return create_trade_read_model_repository_from_path(path)


__all__ = [
    "attach_trade_read_model_repository_to_shared_connection",
    "create_trade_read_model_repository_from_env",
    "create_trade_read_model_repository_from_path",
    "resolve_trade_read_model_persisted_path",
]
