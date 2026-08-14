"""SQLiteでもgive_itemの2所持品更新が同じtransactionへ参加する契約。"""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    SpotGraphItemTransferService,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import CommandEventDispatcher
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_transfer_command_repository_provider import (
    SqliteItemTransferCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import (
    SqliteSpotGraphRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionFactory,
)
from tests.application.world_graph.test_spot_graph_item_transfer_service import (
    OTHER_PLAYER_ID,
    PLAYER_ID,
    SPOT_ID,
    _make_graph_with_player,
    _make_item_spec,
)
from tests.domain.player.aggregate.test_player_status_aggregate import (
    create_test_status_aggregate,
)


def _build_service(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    inventories = SqlitePlayerInventoryWriteRepository.for_standalone_connection(connection)
    items = SqliteItemWriteRepository.for_standalone_connection(connection)
    statuses = SqlitePlayerStatusWriteRepository.for_standalone_connection(connection)
    graph = SqliteSpotGraphRepository.for_standalone_connection(connection)
    graph.save(_make_graph_with_player(SPOT_ID, (PLAYER_ID, OTHER_PLAYER_ID)))
    item = ItemAggregate.create(
        items.generate_item_instance_id(), _make_item_spec(), quantity=1
    )
    items.save(item)
    sender = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    sender.acquire_item(
        item.item_instance_id,
        item_spec_id_value=item.item_spec.item_spec_id.value,
    )
    inventories.save(sender)
    inventories.save(PlayerInventoryAggregate.create_new_inventory(OTHER_PLAYER_ID))
    statuses.save(create_test_status_aggregate(player_id=PLAYER_ID.value))
    statuses.save(create_test_status_aggregate(player_id=OTHER_PLAYER_ID.value))

    dispatcher = CommandEventDispatcher()
    scope_factory = CommandScopeFactory(
        SqliteUnitOfWorkTransactionFactory(database),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=SqliteItemTransferCommandRepositoryProviderFactory(),
    )
    service = SpotGraphItemTransferService(
        spot_graph_repository=graph,
        player_inventory_repository=inventories,
        spot_interior_repository=InMemorySpotInteriorRepository(),
        item_repository=items,
        player_status_repository=statuses,
        item_transfer_command_scope_factory=scope_factory,
    )
    return service, connection, inventories, item.item_instance_id


def test_success_moves_item_between_sqlite_inventories(tmp_path) -> None:
    """正常時はSQLite上でも送り手と受け手を同時に確定する。"""
    service, _, inventories, item_id = _build_service(tmp_path / "game.db")

    service.give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

    sender = inventories.find_by_id(PLAYER_ID)
    recipient = inventories.find_by_id(OTHER_PLAYER_ID)
    assert sender.get_item_instance_id_by_slot(SlotId(0)) is None
    assert recipient.get_item_instance_id_by_slot(SlotId(0)) == item_id


def test_recipient_sql_failure_rolls_back_sender_inventory(tmp_path) -> None:
    """受け手のSQL保存が失敗すると先に実行した送り手更新もrollbackする。"""
    service, connection, inventories, item_id = _build_service(tmp_path / "game.db")
    connection.execute(
        """
        CREATE TRIGGER fail_recipient_inventory
        BEFORE UPDATE ON game_player_inventories
        WHEN NEW.player_id = 2
        BEGIN
            SELECT RAISE(ABORT, 'recipient save failed');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="recipient save failed"):
        service.give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

    sender = inventories.find_by_id(PLAYER_ID)
    recipient = inventories.find_by_id(OTHER_PLAYER_ID)
    assert sender.get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert recipient.get_item_instance_id_by_slot(SlotId(0)) is None
