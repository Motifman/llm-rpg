"""TradeCommandService を SQLite 書き込み 5 リポジトリ＋SqliteUnitOfWork で検証する。"""
from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.application.trade.trade_command_sqlite_wiring import (
    attach_trade_command_sqlite_repositories,
    bootstrap_game_write_schema,
)
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
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)

from tests.application.trade.services.test_trade_command_service import (
    TestTradeCommandService,
    _cmd_trade_listing_projection,
)


class TestTradeCommandServiceSqlite(TestTradeCommandService):
    @pytest.fixture
    def setup_service(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        bootstrap_game_write_schema(conn)
        conn.commit()

        scope, event_publisher = create_sqlite_scope_with_event_publisher(connection=conn)
        (
            shared_trade_repo,
            shared_inv_repo,
            shared_status_repo,
            shared_profile_repo,
            shared_item_repo,
        ) = (
            attach_trade_command_sqlite_repositories(conn, event_sink=scope)
        )

        trade_repo = SqliteTradeAggregateRepository.for_standalone_connection(conn)
        inv_repo = SqlitePlayerInventoryWriteRepository.for_standalone_connection(conn)
        status_repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(conn)
        profile_repo = SqlitePlayerProfileWriteRepository.for_standalone_connection(conn)
        item_repo = SqliteItemWriteRepository.for_standalone_connection(conn)

        service = TradeCommandService(
            shared_trade_repo,
            shared_inv_repo,
            shared_status_repo,
            shared_profile_repo,
            shared_item_repo,
            scope,
        )
        return (
            service,
            trade_repo,
            inv_repo,
            status_repo,
            scope,
            event_publisher,
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

        service, _, _, _, scope, _, _, _ = setup_service
        trade_repo = service._trade_repository  # noqa: SLF001 - shared UoW リポジトリで rollback 採番を検証

        with pytest.raises(RuntimeError, match="abort"):
            with scope:
                tid = trade_repo.generate_trade_id()
                trade = TradeAggregate.create_new_trade(
                    trade_id=tid,
                    seller_id=PlayerId(1),
                    offered_item_id=ItemInstanceId(1),
                    requested_gold=TradeRequestedGold.of(10),
                    created_at=datetime.now(),
                    trade_scope=TradeScope.global_trade(),
                    listing_projection=_cmd_trade_listing_projection(),
                )
                trade_repo.save(trade)
                raise RuntimeError("abort")

        with scope:
            tid2 = trade_repo.generate_trade_id()
        assert tid2.value == 1
        assert trade_repo.find_by_id(TradeId(1)) is None
