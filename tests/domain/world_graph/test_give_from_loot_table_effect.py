"""GIVE_FROM_LOOT_TABLE effect 検証 (PR #1 動的 loot)。

LootTableRepository から抽選した結果を item_spec_ids_to_grant に追加する
ことを確認する。repository 未注入 / loot_table 未登録 のときは silent
skip (warning log のみ) で effect 全体は continue。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import (
    LootEntry,
    LootTableAggregate,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
    InMemoryLootTableRepository,
)


def _make_interior() -> SpotInterior:
    obj = SpotObject(
        object_id=SpotObjectId.create(1),
        name="test_obj", description="t",
        object_type=ObjectTypeEnum.RESOURCE,
        state={}, interactions=(),
    )
    return SpotInterior(
        sub_locations=(), objects=(obj,),
        ground_items=(), discoverable_items=(),
    )


def _make_loot_table(table_id: int, entries: list) -> LootTableAggregate:
    return LootTableAggregate.create(
        loot_table_id=LootTableId.create(table_id),
        entries=entries,
    )


def _apply(svc: WorldGraphEffectService, params: dict):
    effect = InteractionEffect(
        effect_type=InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE,
        parameters=params,
    )
    return svc.apply_effects(
        effects=(effect,),
        interior=_make_interior(),
        acting_object=None,
        world_flags=frozenset(),
    )


class TestBasicLootDrop:
    """LootTable から確実に 1 アイテムが grant される。"""

    def test_single_entry_table_item_rendered(self) -> None:
        """単一 entry の table は常にその item が出る。"""
        repo = InMemoryLootTableRepository()
        repo.save(_make_loot_table(1, [
            LootEntry(item_spec_id=ItemSpecId.create(100), weight=1),
        ]))
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(svc, {"loot_table_id": 1})

        # 単一 entry なので必ず item_spec_id=100 が grant される
        assert any(s.value == 100 for s in result.item_spec_ids_to_grant)

    def test_times_two_2(self) -> None:
        """times 2 で 2 回抽選。"""
        repo = InMemoryLootTableRepository()
        repo.save(_make_loot_table(1, [
            LootEntry(
                item_spec_id=ItemSpecId.create(100),
                weight=1, min_quantity=1, max_quantity=1,
            ),
        ]))
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(svc, {"loot_table_id": 1, "times": 2})

        # 各回 quantity=1 なので合計 2 個 grant される
        assert len([s for s in result.item_spec_ids_to_grant if s.value == 100]) == 2

    def test_min_max_quantity_grant(self) -> None:
        """min max quantity 範囲で grant される。"""
        repo = InMemoryLootTableRepository()
        repo.save(_make_loot_table(1, [
            LootEntry(
                item_spec_id=ItemSpecId.create(100),
                weight=1, min_quantity=3, max_quantity=3,
            ),
        ]))
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(svc, {"loot_table_id": 1})

        # min=max=3 なので必ず 3 個出る
        assert len([s for s in result.item_spec_ids_to_grant if s.value == 100]) == 3


class TestSilentSkip:
    """provider 不在 / table 未登録は silent skip (例外を投げず continue)。"""

    def test_repository_uninjected_silent_skip(self) -> None:
        """repository 未注入なら silent skip。"""
        svc = WorldGraphEffectService()  # repo 無し

        result = _apply(svc, {"loot_table_id": 1})

        # 何も grant されない、例外も投げない
        assert result.item_spec_ids_to_grant == ()

    def test_loot_table_id_unregistered_silent_skip(self) -> None:
        """loottableid が未登録なら silentskip。"""
        repo = InMemoryLootTableRepository()
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(svc, {"loot_table_id": 999})

        assert result.item_spec_ids_to_grant == ()

    def test_loot_table_id_invalid_silent_skip(self) -> None:
        """loottableid が不正なら silentskip。"""
        repo = InMemoryLootTableRepository()
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(svc, {"loot_table_id": "not_an_int"})

        assert result.item_spec_ids_to_grant == ()
