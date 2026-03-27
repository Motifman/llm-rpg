"""Trade ReadModel の composition root 向け: 環境変数またはパスで in-memory / SQLite を切替する。

`TradeQueryService`・`TradePageQueryService`・`TradeEventHandler` には、ファクトリで得た
`TradeReadModelRepository` を**同一インスタンス**で渡すこと。

Trade メイン ReadModel のパスは `resolve_trade_read_model_persisted_path`（`TRADE_READMODEL_DB_PATH`
優先、`GAME_DB_PATH` フォールバック）。Personal / Detail / GlobalMarket をまとめて組むときは
`create_trade_read_model_repositories_bundle_for_app` で **同一ファイル**に揃えられる。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union

from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.domain.trade.repository.global_market_listing_read_model_repository import (
    GlobalMarketListingReadModelRepository,
)
from ai_rpg_world.domain.trade.repository.personal_trade_listing_read_model_repository import (
    PersonalTradeListingReadModelRepository,
)
from ai_rpg_world.domain.trade.repository.trade_detail_read_model_repository import (
    TradeDetailReadModelRepository,
)
from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.global_market_listing_read_model_repository_factory import (
    create_global_market_listing_read_model_repository_from_path,
)
from ai_rpg_world.infrastructure.repository.in_memory_global_market_listing_read_model_repository import (
    InMemoryGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_personal_trade_listing_read_model_repository import (
    InMemoryPersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_detail_read_model_repository import (
    InMemoryTradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.personal_trade_listing_read_model_repository_factory import (
    create_personal_trade_listing_read_model_repository_from_path,
)
from ai_rpg_world.infrastructure.repository.trade_detail_read_model_repository_factory import (
    create_trade_detail_read_model_repository_from_path,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_repository_factory import (
    create_trade_read_model_repository_from_env,
    create_trade_read_model_repository_from_path,
    resolve_trade_read_model_persisted_path,
)


@dataclass(frozen=True)
class TradeReadModelRepositoriesBundle:
    """同一永続化方針で揃えた Trade 系 ReadModel（メイン + 周辺）。"""

    trade_read_model: TradeReadModelRepository
    personal_listing: PersonalTradeListingReadModelRepository
    trade_detail: TradeDetailReadModelRepository
    global_market_listing: GlobalMarketListingReadModelRepository


def create_trade_read_model_repository_for_app(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeReadModelRepository:
    """`TRADE_READMODEL_DB_PATH` を優先し、無ければ `GAME_DB_PATH` で ReadModel リポジトリを返す。"""
    return create_trade_read_model_repository_from_env(environ=environ)


def create_trade_read_model_repository_for_app_from_path(
    db_path: Optional[Union[str, Path]],
) -> TradeReadModelRepository:
    """ファイルパスがあれば SQLite、空なら in-memory。"""
    return create_trade_read_model_repository_from_path(db_path)


def create_trade_read_model_repositories_bundle_for_app(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeReadModelRepositoriesBundle:
    """Trade メインと Personal / Detail / GlobalMarket を同一 SQLite ファイル（またはすべて in-memory）で構築する。

    永続化パスは `resolve_trade_read_model_persisted_path` と同一。クエリ系サービスへは各フィールドの
    インスタンスを**そのまま**渡し、取引所まわりで実装を混在させないこと。
    """
    path = resolve_trade_read_model_persisted_path(environ=environ)
    if path is None:
        return TradeReadModelRepositoriesBundle(
            trade_read_model=InMemoryTradeReadModelRepository(),
            personal_listing=InMemoryPersonalTradeListingReadModelRepository(),
            trade_detail=InMemoryTradeDetailReadModelRepository(),
            global_market_listing=InMemoryGlobalMarketListingReadModelRepository(),
        )
    return TradeReadModelRepositoriesBundle(
        trade_read_model=create_trade_read_model_repository_from_path(path),
        personal_listing=create_personal_trade_listing_read_model_repository_from_path(path),
        trade_detail=create_trade_detail_read_model_repository_from_path(path),
        global_market_listing=create_global_market_listing_read_model_repository_from_path(path),
    )


def create_trade_query_service_for_app(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> TradeQueryService:
    """環境に応じた ReadModel 実装で `TradeQueryService` を組み立てる。"""
    repo = create_trade_read_model_repository_from_env(environ=environ)
    return TradeQueryService(repo)


__all__ = [
    "TradeReadModelRepositoriesBundle",
    "create_trade_query_service_for_app",
    "create_trade_read_model_repositories_bundle_for_app",
    "create_trade_read_model_repository_for_app",
    "create_trade_read_model_repository_for_app_from_path",
    "resolve_trade_read_model_persisted_path",
]
