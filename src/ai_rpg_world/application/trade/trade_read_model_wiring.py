"""Trade ReadModel の composition root 向け: 環境変数またはパスで in-memory / SQLite を切替する。

`TradeQueryService`・`TradePageQueryService`・`TradeEventHandler` には、ファクトリで得た
`TradeReadModelRepository` を**同一インスタンス**で渡すこと。
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_repository_factory import (
    create_trade_read_model_repository_from_env,
    create_trade_read_model_repository_from_path,
)


def create_trade_read_model_repository_for_app(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeReadModelRepository:
    """環境変数 `TRADE_READMODEL_DB_PATH` に基づき ReadModel リポジトリを返す。"""
    return create_trade_read_model_repository_from_env(environ=environ)


def create_trade_read_model_repository_for_app_from_path(
    db_path: Optional[Union[str, Path]],
) -> TradeReadModelRepository:
    """ファイルパスがあれば SQLite、空なら in-memory。"""
    return create_trade_read_model_repository_from_path(db_path)


def create_trade_query_service_for_app(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeQueryService:
    """環境に応じた ReadModel 実装で `TradeQueryService` を組み立てる。"""
    repo = create_trade_read_model_repository_for_app(environ=environ)
    return TradeQueryService(repo)


__all__ = [
    "create_trade_read_model_repository_for_app",
    "create_trade_read_model_repository_for_app_from_path",
    "create_trade_query_service_for_app",
]
