"""SQLiteでもdrop/pickupが所持品と地面を同時に確定する契約。"""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    SpotGraphItemTransferService,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_transfer_command_repository_provider import (  # noqa: E501
    SqliteItemTransferCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import (
    SqliteSpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import (
    SqliteSpotInteriorRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionFactory,
)
from tests.application.world_graph.test_spot_graph_item_transfer_service import (
    PLAYER_ID,
    SPOT_ID,
    _make_graph_with_player,
    _make_item_spec,
)


def _build_service(database, *, item_on_ground: bool = False):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    inventories = SqlitePlayerInventoryWriteRepository.for_standalone_connection(
        connection
    )
    items = SqliteItemWriteRepository.for_standalone_connection(connection)
    graph = SqliteSpotGraphRepository.for_standalone_connection(connection)
    interiors = SqliteSpotInteriorRepository.for_standalone_connection(connection)
    graph.save(_make_graph_with_player(SPOT_ID, (PLAYER_ID,)))

    item = ItemAggregate.create(
        items.generate_item_instance_id(), _make_item_spec(), quantity=1
    )
    items.save(item)
    inventory = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    if not item_on_ground:
        inventory.acquire_item(
            item.item_instance_id,
            item_spec_id_value=item.item_spec.item_spec_id.value,
        )
    inventories.save(inventory)
    interior = SpotInterior.empty()
    if item_on_ground:
        interior = interior.with_ground_item(
            GroundItem(item.item_instance_id, item.item_spec.item_spec_id)
        )
    interiors.save(SPOT_ID, interior)

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
        spot_interior_repository=interiors,
        item_repository=items,
        item_transfer_command_scope_factory=scope_factory,
    )
    return service, connection, inventories, interiors, item.item_instance_id


def _reject_interior_write(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TRIGGER fail_interior_write
        BEFORE INSERT ON spot_graph_interior
        BEGIN
            SELECT RAISE(ABORT, 'interior save failed');
        END
        """
    )
    connection.commit()


def test_sqlite_drop_and_pickup_commit_both_resources(tmp_path) -> None:
    """正常なdropとpickupはSQLite上の所持品と地面を同時に往復させる。"""
    service, _, inventories, interiors, item_id = _build_service(
        tmp_path / "game.db"
    )

    service.drop_item(PLAYER_ID, SlotId(0))
    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) is None
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is not None

    service.pickup_item(PLAYER_ID, item_id)
    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is None


def test_sqlite_drop_interior_failure_rolls_back_inventory(tmp_path) -> None:
    """dropの地面SQL失敗時は先行したinventory更新もrollbackする。"""
    service, connection, inventories, interiors, item_id = _build_service(
        tmp_path / "game.db"
    )
    _reject_interior_write(connection)

    with pytest.raises(sqlite3.IntegrityError, match="interior save failed"):
        service.drop_item(PLAYER_ID, SlotId(0))

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is None


def test_sqlite_pickup_interior_failure_rolls_back_inventory(tmp_path) -> None:
    """pickupの地面SQL失敗時は先行した取得もrollbackする。"""
    service, connection, inventories, interiors, item_id = _build_service(
        tmp_path / "game.db", item_on_ground=True
    )
    _reject_interior_write(connection)

    with pytest.raises(sqlite3.IntegrityError, match="interior save failed"):
        service.pickup_item(PLAYER_ID, item_id)

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) is None
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is not None
