"""Phase 9 integration checks for the unified SQLite game DB."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.social.social_sqlite_wiring import (
    attach_social_sqlite_repositories,
)
from ai_rpg_world.application.static_master_sqlite_wiring import (
    attach_static_master_sqlite_repositories,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)


def _item_spec(item_spec_id: int = 1) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name=f"item-{item_spec_id}",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="phase9 item",
        max_stack_size=MaxStackSize(20),
    )


def _item_aggregate(item_spec: ItemSpec, item_instance_id: int = 101) -> ItemAggregate:
    return ItemAggregate.create_from_instance(
        ItemInstance(
            item_instance_id=ItemInstanceId(item_instance_id),
            item_spec=item_spec,
            quantity=3,
        )
    )


def test_same_transaction_visibility_across_static_master_and_world_state() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    uow = SqliteUnitOfWork(connection=conn)

    with uow:
        static_master = attach_static_master_sqlite_repositories(uow.connection)
        world_state = attach_world_state_sqlite_repositories(uow.connection, event_sink=uow)
        spec = _item_spec(1)

        static_master.writers.item_specs.replace_spec(spec)
        world_state.player_state.items.save(_item_aggregate(spec))

        loaded_spec = static_master.readers.item_specs.find_by_id(ItemSpecId(1))
        loaded_item = world_state.player_state.items.find_by_id(ItemInstanceId(101))

        assert loaded_spec is not None
        assert loaded_item is not None
        assert loaded_item.item_spec.item_spec_id == ItemSpecId(1)


def test_cross_bundle_rollback_reverts_uncommitted_writes(tmp_path) -> None:
    db = tmp_path / "phase9.db"
    factory = SqliteUnitOfWorkFactory(db)

    with factory.create() as bootstrap:
        attach_static_master_sqlite_repositories(bootstrap.connection)
        attach_world_state_sqlite_repositories(bootstrap.connection, event_sink=bootstrap)

    with pytest.raises(RuntimeError, match="abort"):
        with factory.create() as uow:
            static_master = attach_static_master_sqlite_repositories(uow.connection)
            world_state = attach_world_state_sqlite_repositories(
                uow.connection, event_sink=uow
            )
            spec = _item_spec(2)

            static_master.writers.item_specs.replace_spec(spec)
            world_state.player_state.items.save(_item_aggregate(spec, item_instance_id=202))
            raise RuntimeError("abort")

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM game_item_specs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM game_items").fetchone()[0] == 0
    finally:
        conn.close()


def test_event_sink_collects_events_inside_sqlite_scope() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    scope, _publisher = create_sqlite_scope_with_event_publisher(connection=conn)

    with scope:
        social = attach_social_sqlite_repositories(scope.connection, event_sink=scope)
        social.users.save(
            UserAggregate.create_new_user(
                user_id=UserId(10),
                user_name="phase9",
                display_name="Phase 9",
                bio="integration",
            )
        )

        pending, processed_count = scope.get_pending_events_since(0)
        assert processed_count >= 1
        assert len(pending) >= 1
