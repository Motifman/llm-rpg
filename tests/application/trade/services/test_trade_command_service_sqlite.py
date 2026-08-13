"""TradeCommandService を SQLite 書き込み 5 リポジトリ＋SqliteUnitOfWork で検証する。"""
from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.application.trade.trade_command_sqlite_wiring import bootstrap_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import (
    SqliteTradeAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_repository_provider import (
    SqliteTradeCommandRepositoryProviderFactory,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionFactory,
)

from tests.application.trade.services.test_trade_command_service import (
    TestTradeCommandService,
    _cmd_trade_listing_projection,
    _NoOpAfterCommitHandoff,
    _NoOpSyncDispatcher,
)


class TestTradeCommandServiceSqlite(TestTradeCommandService):
    @pytest.fixture
    def setup_service(self, tmp_path):
        database = tmp_path / "game.db"
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        bootstrap_game_write_schema(conn)
        conn.commit()

        trade_repo = SqliteTradeAggregateRepository.for_standalone_connection(conn)
        inv_repo = SqlitePlayerInventoryWriteRepository.for_standalone_connection(conn)
        status_repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(conn)
        profile_repo = SqlitePlayerProfileWriteRepository.for_standalone_connection(conn)
        item_repo = SqliteItemWriteRepository.for_standalone_connection(conn)

        scope_factory = CommandScopeFactory(
            SqliteUnitOfWorkTransactionFactory(database),
            sync_dispatcher=_NoOpSyncDispatcher(),  # type: ignore[arg-type]
            after_commit_handoff=_NoOpAfterCommitHandoff(),  # type: ignore[arg-type]
            repository_provider_factory=(
                SqliteTradeCommandRepositoryProviderFactory()
            ),
        )
        service = TradeCommandService(scope_factory)
        return (
            service,
            trade_repo,
            inv_repo,
            status_repo,
            scope_factory,
            None,
            profile_repo,
            item_repo,
        )

    def test_trade_id_sequence_rolls_back_with_failed_transaction(self, setup_service):
        """UoW 内で採番した trade_id は rollback 後に永続化されず、採番も巻き戻る。"""
        from datetime import datetime

        from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
        from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
        from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope

        _, trade_repo, _, _, scope_factory, _, _, _ = setup_service

        with pytest.raises(RuntimeError, match="abort"):
            with scope_factory.create() as context:
                scoped_trade_repo = context.repositories.trades
                tid = scoped_trade_repo.generate_trade_id()
                trade = TradeAggregate.create_new_trade(
                    trade_id=tid,
                    seller_id=PlayerId(1),
                    offered_item_id=ItemInstanceId(1),
                    requested_gold=TradeRequestedGold.of(10),
                    created_at=datetime.now(),
                    trade_scope=TradeScope.global_trade(),
                    listing_projection=_cmd_trade_listing_projection(),
                )
                scoped_trade_repo.save(trade)
                raise RuntimeError("abort")

        with scope_factory.create() as context:
            tid2 = context.repositories.trades.generate_trade_id()
        assert tid2.value == 1
        assert trade_repo.find_by_id(TradeId(1)) is None
