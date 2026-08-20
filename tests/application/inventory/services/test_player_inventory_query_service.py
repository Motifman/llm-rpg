"""PlayerInventoryQueryService.list_held_items の仕様を保証するテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.inventory.services.player_inventory_query_service import (
    PlayerInventoryQueryService,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


def _new_inv(player_id_val: int = 1, max_slots: int = 4) -> PlayerInventoryAggregate:
    return PlayerInventoryAggregate.create_new_inventory(
        player_id=PlayerId(player_id_val),
        max_slots=max_slots,
    )


def _item_spec(
    spec_id: int,
    *,
    name: str = "テスト品",
    description: str = "説明文",
) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(spec_id),
        name=name,
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description=description,
        max_stack_size=MaxStackSize(64),
    )


def _item(
    iid: int,
    spec_id: int,
    *,
    name: str = "テスト品",
    description: str = "説明文",
    state: dict | None = None,
) -> ItemAggregate:
    return ItemAggregate.create(
        ItemInstanceId(iid),
        _item_spec(spec_id, name=name, description=description),
        state=state,
    )


@pytest.fixture
def repos() -> tuple[
    InMemoryPlayerInventoryRepository,
    InMemoryItemRepository,
    PlayerInventoryQueryService,
]:
    data_store = InMemoryDataStore()
    data_store.clear_all()

    def create_uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

    uow, _ = InMemoryUnitOfWork.create_with_event_publisher(
        unit_of_work_factory=create_uow,
        data_store=data_store,
    )
    inv_repo = InMemoryPlayerInventoryRepository(data_store, uow)
    item_repo = InMemoryItemRepository(data_store, uow)
    service = PlayerInventoryQueryService(inv_repo, item_repo)
    return inv_repo, item_repo, service


class TestPlayerInventoryQueryService:
    """この照会が所持スロットを公開 API で読み、spec_id だけで個数をまとめることを保証する。"""

    def test_empty_inventory_returns_empty_items(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """所持品が 1 つも無い inventory なら items は空 tuple。"""
        inv_repo, _, service = repos
        player_id = PlayerId(1)
        inv_repo.save(_new_inv(max_slots=4))

        view = service.list_held_items(player_id)

        assert view.items == ()

    def test_missing_inventory_aggregate_returns_empty_items(
        self,
        repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """repo に inventory 集約が無い player_id なら items は空 tuple。"""
        _, _, service = repos

        view = service.list_held_items(PlayerId(99))

        assert view.items == ()

    def test_same_spec_in_multiple_slots_is_aggregated(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """同じ item_spec_id が複数スロットにあるとき quantity を合算し行は 1 つ。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv.acquire_item(ItemInstanceId(7002))
        inv_repo.save(inv)
        item_repo.save(_item(7001, 101))
        item_repo.save(_item(7002, 101))

        view = service.list_held_items(player_id)

        assert len(view.items) == 1
        assert view.items[0].item_spec_id == 101
        assert view.items[0].quantity == 2

    def test_different_specs_are_separate_rows_in_encounter_order(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """異なる spec は別行になり、先に occupied で見えた spec が先に並ぶ。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv.acquire_item(ItemInstanceId(7002))
        inv_repo.save(inv)
        item_repo.save(_item(7001, 101, name="先", description="先の説明"))
        item_repo.save(_item(7002, 202, name="後", description="後の説明"))

        view = service.list_held_items(player_id)

        assert len(view.items) == 2
        assert view.items[0].item_spec_id == 101
        assert view.items[0].name == "先"
        assert view.items[1].item_spec_id == 202
        assert view.items[1].name == "後"

    def test_spoiled_and_fresh_same_spec_are_one_row(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """同じ spec の腐敗品と新鮮品は 1 行に合算し、is_spoiled で分けない。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv.acquire_item(ItemInstanceId(7002))
        inv_repo.save(inv)
        item_repo.save(_item(7001, 101, state={"spoiled": False}))
        item_repo.save(_item(7002, 101, state={"spoiled": True}))

        view = service.list_held_items(player_id)

        assert len(view.items) == 1
        assert view.items[0].item_spec_id == 101
        assert view.items[0].quantity == 2

    def test_empty_slots_are_not_listed(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """max_slots=4 で 1 個だけ所持しているとき、行は 1 つだけ。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv_repo.save(inv)
        item_repo.save(_item(7001, 101))

        view = service.list_held_items(player_id)

        assert len(view.items) == 1
        assert view.items[0].quantity == 1

    def test_missing_item_instance_is_skipped(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """item repo に実体が無い item_instance_id はスキップする。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv.acquire_item(ItemInstanceId(7002))
        inv_repo.save(inv)
        item_repo.save(_item(7001, 101))
        # 7002 は repo に保存しない

        view = service.list_held_items(player_id)

        assert len(view.items) == 1
        assert view.items[0].item_spec_id == 101
        assert view.items[0].quantity == 1

    def test_equipped_items_are_not_listed(
        self, repos: tuple[
            InMemoryPlayerInventoryRepository,
            InMemoryItemRepository,
            PlayerInventoryQueryService,
        ],
    ) -> None:
        """装備スロットだけにある品は一覧に出さない。"""
        inv_repo, item_repo, service = repos
        player_id = PlayerId(1)
        inv = _new_inv(max_slots=4)
        inv.acquire_item(ItemInstanceId(7001))
        inv.complete_equip_item(
            SlotId(0),
            EquipmentSlotType.WEAPON,
            ItemInstanceId(7001),
        )
        inv_repo.save(inv)
        item_repo.save(
            ItemAggregate.create(
                ItemInstanceId(7001),
                ItemSpec(
                    item_spec_id=ItemSpecId(101),
                    name="装備中の剣",
                    item_type=ItemType.EQUIPMENT,
                    rarity=Rarity.COMMON,
                    description="装備品",
                    max_stack_size=MaxStackSize(1),
                    durability_max=100,
                    equipment_type=EquipmentType.WEAPON,
                ),
            )
        )

        view = service.list_held_items(player_id)

        assert view.items == ()

    def test_uses_iter_occupied_slots_not_slot_index_loop(self) -> None:
        """走査は iter_occupied_slots を使い、スロット番号ループ用 API は使わない。"""
        inv_repo = MagicMock()
        item_repo = MagicMock()
        inv = MagicMock()
        inv.iter_occupied_slots.return_value = []
        inv_repo.find_by_id.return_value = inv
        service = PlayerInventoryQueryService(inv_repo, item_repo)

        service.list_held_items(PlayerId(1))

        inv.iter_occupied_slots.assert_called_once()
        inv.get_item_instance_id_by_slot.assert_not_called()
