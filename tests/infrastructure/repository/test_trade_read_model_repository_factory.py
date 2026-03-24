"""Trade ReadModel リポジトリファクトリのテスト"""

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.event.trade_event import TradeOfferedEvent
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_repository import InMemoryTradeRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_repository_factory import (
    create_trade_read_model_repository_from_env,
    create_trade_read_model_repository_from_path,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class TestTradeReadModelRepositoryFactory:
    def test_none_or_empty_string_uses_in_memory(self) -> None:
        assert isinstance(
            create_trade_read_model_repository_from_path(None),
            InMemoryTradeReadModelRepository,
        )
        assert isinstance(
            create_trade_read_model_repository_from_path(""),
            InMemoryTradeReadModelRepository,
        )
        assert isinstance(
            create_trade_read_model_repository_from_path("   "),
            InMemoryTradeReadModelRepository,
        )

    def test_path_uses_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "trm.db"
        repo = create_trade_read_model_repository_from_path(db)
        assert isinstance(repo, SqliteTradeReadModelRepository)

    def test_persistence_visible_from_new_connection(self, tmp_path: Path) -> None:
        db = tmp_path / "trm.db"
        repo1 = create_trade_read_model_repository_from_path(db)
        assert isinstance(repo1, SqliteTradeReadModelRepository)
        m = TradeReadModel.create_from_trade_and_item(
            trade_id=TradeId(42),
            seller_id=PlayerId(1),
            seller_name="s",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=ItemInstanceId(42),
            item_name="i",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_description="d",
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=10,
            durability_max=10,
            requested_gold=TradeRequestedGold.of(100),
            status=TradeStatus.ACTIVE,
            created_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        repo1.save(m)

        conn2 = sqlite3.connect(str(db))
        repo2 = SqliteTradeReadModelRepository(conn2)
        loaded = repo2.find_by_id(TradeId(42))
        assert loaded is not None
        assert loaded.trade_id == 42

    def test_from_env_empty_uses_in_memory(self) -> None:
        repo = create_trade_read_model_repository_from_env(environ={})
        assert isinstance(repo, InMemoryTradeReadModelRepository)

    def test_from_env_set_uses_sqlite(self, tmp_path: Path) -> None:
        db = tmp_path / "env.db"
        repo = create_trade_read_model_repository_from_env(
            environ={"TRADE_READMODEL_DB_PATH": str(db)},
        )
        assert isinstance(repo, SqliteTradeReadModelRepository)

    def test_trade_event_handler_offered_persists_via_factory_sqlite(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "handler.db"
        read_model_repo = create_trade_read_model_repository_from_path(db)
        assert isinstance(read_model_repo, SqliteTradeReadModelRepository)

        def create_uow() -> InMemoryUnitOfWork:
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        trade_repo = InMemoryTradeRepository()
        profile_repo = InMemoryPlayerProfileRepository()
        item_instance_repo = Mock()
        uow_factory = Mock()
        uow_factory.create.side_effect = create_uow

        handler = TradeEventHandler(
            read_model_repo,
            trade_repo,
            profile_repo,
            item_instance_repo,
            uow_factory,
        )

        seller_id = PlayerId(1)
        profile = PlayerProfileAggregate.create(seller_id, PlayerName("Seller"))
        profile_repo.save(profile)

        item_id = ItemInstanceId(100)
        mock_item = Mock()
        mock_item.item_spec.name = "Test Item"
        mock_item.item_spec.item_type = ItemType.CONSUMABLE
        mock_item.item_spec.rarity = Rarity.COMMON
        mock_item.item_spec.description = "Test Desc"
        mock_item.quantity = 1
        mock_item.durability = None
        item_instance_repo.find_by_id.return_value = mock_item

        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=seller_id,
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            trade_scope=TradeScope.global_trade(),
        )

        handler.handle_trade_offered(event)

        conn2 = sqlite3.connect(str(db))
        repo2 = SqliteTradeReadModelRepository(conn2)
        read_back = repo2.find_by_id(TradeId(1))
        assert read_back is not None
        assert read_back.seller_name == "Seller"
        assert read_back.item_name == "Test Item"
        assert read_back.status == "ACTIVE"
