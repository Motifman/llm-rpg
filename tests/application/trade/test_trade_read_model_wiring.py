"""`trade_read_model_wiring` が環境に応じて正しいリポジトリ実装へ接続すること。"""

from pathlib import Path

from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.application.trade.trade_read_model_wiring import (
    create_trade_query_service_for_app,
    create_trade_read_model_repository_for_app,
    create_trade_read_model_repository_for_app_from_path,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
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
