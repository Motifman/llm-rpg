"""GIVE_FROM_LOOT_TABLE effect 検証 (PR #1 動的 loot)。

LootTableRepository から抽選した結果を item_spec_ids_to_grant に追加する
ことを確認する。repository 未注入 / loot_table 未登録 のときは silent
skip (warning log のみ) で effect 全体は continue。
"""

from __future__ import annotations

import logging

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
        name="test_obj",
        description="t",
        object_type=ObjectTypeEnum.RESOURCE,
        state={},
        interactions=(),
    )
    return SpotInterior(
        sub_locations=(),
        objects=(obj,),
        ground_items=(),
        discoverable_items=(),
    )


def _make_loot_table(table_id: int, entries: list) -> LootTableAggregate:
    return LootTableAggregate.create(
        loot_table_id=LootTableId.create(table_id),
        entries=entries,
    )


def _apply(svc: WorldGraphEffectService, params: dict, *, following=()):
    effect = InteractionEffect(
        effect_type=InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE,
        parameters=params,
    )
    return svc.apply_effects(
        effects=(effect, *following),
        interior=_make_interior(),
        acting_object=None,
        world_flags=frozenset(),
    )


class TestBasicLootDrop:
    """選んだ抽選表の品目と、抽選回数・当選数量に応じた付与数を保証する。"""

    @pytest.mark.parametrize(
        ("table_id", "quantity", "params", "expected"),
        [
            (1, 1, {"loot_table_id": 1}, (100,)),
            (1, 1, {"loot_table_id": 1, "times": 2}, (100, 100)),
            (1, 3, {"loot_table_id": 1}, (100, 100, 100)),
            (9, 2, {"loot_table_id": 9, "times": 3}, (108, 108, 108, 108, 108, 108)),
        ],
    )
    def test_selected_table_grants_exact_items(self, table_id, quantity, params, expected) -> None:
        """指定した抽選表の品目を既定1回または指定回数だけ抽選し、数量ぶんだけ付与する。"""
        repo = InMemoryLootTableRepository()
        if table_id != 1:
            repo.save(_make_loot_table(1, [LootEntry(ItemSpecId.create(999), weight=1)]))
        repo.save(
            _make_loot_table(
                table_id,
                [
                    LootEntry(
                        item_spec_id=ItemSpecId.create(100 if table_id == 1 else 108),
                        weight=1,
                        min_quantity=quantity,
                        max_quantity=quantity,
                    )
                ],
            )
        )

        result = _apply(WorldGraphEffectService(loot_table_repository=repo), params)

        assert tuple(s.value for s in result.item_spec_ids_to_grant) == expected


class TestSilentSkip:
    """抽選元なし・表なし・不正IDは原因を警告し、他の効果を止めない。"""

    def test_repository_uninjected_silent_skip(self, caplog) -> None:
        """抽選Repository未注入は警告し、付与なしで後続の効果を続ける。"""
        svc = WorldGraphEffectService()  # repo 無し

        result = _apply(
            svc,
            {"loot_table_id": 1},
            following=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                    parameters={"message": "採取を続ける"},
                ),
            ),
        )

        # 何も grant されない、例外も投げない
        assert result.item_spec_ids_to_grant == ()
        assert result.messages == ("採取を続ける",)
        assert any(
            record.levelno == logging.WARNING
            and "GIVE_FROM_LOOT_TABLE" in record.message
            and all(token in record.message for token in ("not injected",))
            for record in caplog.records
        )

    def test_loot_table_id_unregistered_silent_skip(self, caplog) -> None:
        """未登録の抽選表IDは原因を警告し、付与なしで後続の効果を続ける。"""
        repo = InMemoryLootTableRepository()
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(
            svc,
            {"loot_table_id": 999},
            following=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                    parameters={"message": "採取を続ける"},
                ),
            ),
        )

        assert result.item_spec_ids_to_grant == ()
        assert result.messages == ("採取を続ける",)
        assert any(
            record.levelno == logging.WARNING
            and "GIVE_FROM_LOOT_TABLE" in record.message
            and all(token in record.message for token in ("999", "not found"))
            for record in caplog.records
        )

    def test_loot_table_id_invalid_silent_skip(self, caplog) -> None:
        """整数にできない抽選表IDは原因を警告し、付与なしで後続の効果を続ける。"""
        repo = InMemoryLootTableRepository()
        svc = WorldGraphEffectService(loot_table_repository=repo)

        result = _apply(
            svc,
            {"loot_table_id": "not_an_int"},
            following=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                    parameters={"message": "採取を続ける"},
                ),
            ),
        )

        assert result.item_spec_ids_to_grant == ()
        assert result.messages == ("採取を続ける",)
        assert any(
            record.levelno == logging.WARNING
            and "GIVE_FROM_LOOT_TABLE" in record.message
            and all(token in record.message for token in ("not_an_int", "invalid"))
            for record in caplog.records
        )


class TestSeededLootDrop:
    """渡した乱数源で抽選し、同じ種なら同じ結果になることを保証する (#1514)。"""

    @staticmethod
    def _service(seed: int) -> WorldGraphEffectService:
        import random

        repo = InMemoryLootTableRepository()
        repo.save(
            _make_loot_table(
                1,
                [
                    LootEntry(item_spec_id=ItemSpecId.create(100 + i), weight=1, min_quantity=1, max_quantity=3)
                    for i in range(5)
                ],
            )
        )
        return WorldGraphEffectService(loot_table_repository=repo, random_source=random.Random(seed))

    def test_same_seed_grants_the_same_items(self) -> None:
        """同じ種の乱数源を渡した 2 つの service は 30 回の抽選で同じ物を同じ数だけ渡し、別の種なら違う物を渡す。"""
        first, second = self._service(7), self._service(7)

        grants = [
            _apply(svc, {"loot_table_id": 1, "times": 30}).item_spec_ids_to_grant
            for svc in (first, second, self._service(8))
        ]

        assert grants[0] == grants[1]
        assert grants[0] != grants[2]

    def test_module_random_does_not_change_the_result(self) -> None:
        """モジュール全体の乱数を動かしても、渡した乱数源の抽選結果は変わらない。"""
        import random

        random.seed(1)
        first = _apply(self._service(7), {"loot_table_id": 1, "times": 30}).item_spec_ids_to_grant
        random.seed(2)
        second = _apply(self._service(7), {"loot_table_id": 1, "times": 30}).item_spec_ids_to_grant

        assert first == second
