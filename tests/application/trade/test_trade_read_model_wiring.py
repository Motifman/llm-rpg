"""`trade_read_model_wiring` が環境に応じて正しいリポジトリ実装へ接続すること。"""

from pathlib import Path

from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.application.trade.trade_read_model_wiring import (
    create_trade_query_service_for_app,
    create_trade_read_model_repositories_bundle_for_app,
    create_trade_read_model_repository_for_app,
    create_trade_read_model_repository_for_app_from_path,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_global_market_listing_read_model_repository import (
    SqliteGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_personal_trade_listing_read_model_repository import (
    SqlitePersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_detail_read_model_repository import (
    SqliteTradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)


class TestTradeReadModelWiring:
    def test_repository_for_app_empty_env_uses_in_memory(self) -> None:
        repo = create_trade_read_model_repository_for_app(environ={})
        assert isinstance(repo, InMemoryTradeReadModelRepository)

    def test_repository_for_app_from_path_none_uses_in_memory(self) -> None:
        repo = create_trade_read_model_repository_for_app_from_path(None)
        assert isinstance(repo, InMemoryTradeReadModelRepository)

    def test_repository_for_app_from_path_uses_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "w.db"
        repo = create_trade_read_model_repository_for_app_from_path(db)
        assert isinstance(repo, SqliteTradeReadModelRepository)

    def test_query_service_for_app_respects_env_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "q.db"
        svc = create_trade_query_service_for_app(
            environ={"TRADE_READMODEL_DB_PATH": str(db)},
        )
        assert isinstance(svc, TradeQueryService)
        assert isinstance(svc._trade_read_model_repository, SqliteTradeReadModelRepository)

    def test_query_service_for_app_empty_env_uses_in_memory(self) -> None:
        svc = create_trade_query_service_for_app(environ={})
        assert isinstance(svc._trade_read_model_repository, InMemoryTradeReadModelRepository)

    def test_query_service_for_app_uses_game_db_path(self, tmp_path) -> None:
        db = tmp_path / "bundle_q.db"
        svc = create_trade_query_service_for_app(environ={"GAME_DB_PATH": str(db)})
        assert isinstance(svc._trade_read_model_repository, SqliteTradeReadModelRepository)

    def test_bundle_all_sqlite_on_game_db_path(self, tmp_path) -> None:
        db = tmp_path / "bundle.db"
        b = create_trade_read_model_repositories_bundle_for_app(
            environ={"GAME_DB_PATH": str(db)},
        )
        assert isinstance(b.trade_read_model, SqliteTradeReadModelRepository)
        assert isinstance(b.personal_listing, SqlitePersonalTradeListingReadModelRepository)
        assert isinstance(b.trade_detail, SqliteTradeDetailReadModelRepository)
        assert isinstance(b.global_market_listing, SqliteGlobalMarketListingReadModelRepository)
