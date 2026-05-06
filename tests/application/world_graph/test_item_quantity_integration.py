"""Phase 2-A 数量セマンティクスのアプリケーション層 integration test。

`SpotInteractionApplicationService` 経由で、
- HAS_ITEM の required_quantity チェック
- REMOVE_ITEM の quantity 消費
- GIVE_ITEM の quantity 付与
- inventory helper `count_owned_item_instances_by_spec` の重複保持数集計
が end-to-end で動くことを保証する。

シナリオ例: 「鉄鉱石 2 個 + 燃料 1 個でインゴット 3 個を生成する」
小規模クラフト。Phase 1 では書けなかった「複数個要求 / 複数個生成」を
1 つの interaction で表現できることを示す。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


PLAYER_ID = 1
SPOT_ID = 1
FORGE_OBJECT_ID = 10
ORE_SPEC_ID = ItemSpecId.create(100)
COAL_SPEC_ID = ItemSpecId.create(101)
INGOT_SPEC_ID = ItemSpecId.create(102)


def _build_app(initial_items: tuple[ItemSpecId, ...]):
    """forge オブジェクトと指定アイテムを所持したプレイヤーを構築する。"""
    forge_recipe = InteractionDef(
        action_name="craft_ingots",
        display_label="インゴットを 3 個鍛造",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=ORE_SPEC_ID,
                required_quantity=2,
                failure_message="鉄鉱石が 2 個必要です",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=COAL_SPEC_ID,
                required_quantity=1,
                failure_message="燃料が 1 個必要です",
            ),
        ),
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
                parameters={"item_spec_id": ORE_SPEC_ID.value, "quantity": 2},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
                parameters={"item_spec_id": COAL_SPEC_ID.value, "quantity": 1},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
                parameters={"item_spec_id": INGOT_SPEC_ID.value, "quantity": 3},
            ),
        ),
    )
    forge = SpotObject(
        object_id=SpotObjectId.create(FORGE_OBJECT_ID),
        name="forge",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(forge_recipe,),
    )
    spot = SpotNode(
        spot_id=SpotId.create(SPOT_ID),
        name="smithy",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(spot)
    graph.place_entity(EntityId.create(PLAYER_ID), SpotId.create(SPOT_ID))
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (forge,), (), ()))

    data_store = InMemoryDataStore()
    status_repo = InMemoryPlayerStatusRepository(data_store)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    for spec_id, name in [
        (ORE_SPEC_ID, "鉄鉱石"),
        (COAL_SPEC_ID, "石炭"),
        (INGOT_SPEC_ID, "鉄インゴット"),
    ]:
        item_spec_repo.save(
            ItemSpecReadModel(
                item_spec_id=spec_id,
                name=name,
                item_type=ItemType.MATERIAL,
                rarity=Rarity.COMMON,
                description=name,
                max_stack_size=MaxStackSize(99),
            )
        )

    inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(PLAYER_ID)))
    if initial_items:
        grant_item_specs_to_inventory(
            PlayerId(PLAYER_ID), initial_items,
            item_repo, item_spec_repo, inventory_repo,
        )

    flags = MutableWorldFlagState()
    app = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        player_status_repository=status_repo,
    )
    return app, inventory_repo, item_repo


def _counts(inventory_repo, item_repo) -> dict[ItemSpecId, int]:
    inv = inventory_repo.find_by_id(PlayerId(PLAYER_ID))
    return dict(count_owned_item_instances_by_spec(inv, item_repo))


class TestQuantityIntegration:
    """Phase 2-A 数量セマンティクスのアプリ層連動。"""

    def test_craft_succeeds_with_exact_quantities(self) -> None:
        """鉱石 2 + 石炭 1 を持っていればクラフトが成立し、消費 + 3 個生成される。"""
        app, inventory_repo, item_repo = _build_app(
            initial_items=(ORE_SPEC_ID, ORE_SPEC_ID, COAL_SPEC_ID),
        )
        # 投入前: 鉱石 2, 石炭 1, インゴット 0
        before = _counts(inventory_repo, item_repo)
        assert before.get(ORE_SPEC_ID) == 2
        assert before.get(COAL_SPEC_ID) == 1
        assert INGOT_SPEC_ID not in before

        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(FORGE_OBJECT_ID),
            "craft_ingots",
        )
        after = _counts(inventory_repo, item_repo)
        # 鉱石・石炭は消費されてゼロ、インゴット 3 個入手
        assert after.get(ORE_SPEC_ID, 0) == 0
        assert after.get(COAL_SPEC_ID, 0) == 0
        assert after.get(INGOT_SPEC_ID) == 3

    def test_craft_fails_when_ore_insufficient(self) -> None:
        """鉱石が 1 個しかない場合は HAS_ITEM (required_quantity=2) で拒否。"""
        app, inventory_repo, item_repo = _build_app(
            initial_items=(ORE_SPEC_ID, COAL_SPEC_ID),  # 鉱石 1, 石炭 1
        )
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(FORGE_OBJECT_ID),
                "craft_ingots",
            )
        # 失敗時はインベントリ不変
        counts = _counts(inventory_repo, item_repo)
        assert counts.get(ORE_SPEC_ID) == 1
        assert counts.get(COAL_SPEC_ID) == 1

    def test_craft_fails_when_coal_missing(self) -> None:
        """鉱石は 2 個あっても燃料が無ければ拒否。"""
        app, _, _ = _build_app(
            initial_items=(ORE_SPEC_ID, ORE_SPEC_ID),  # 鉱石 2, 石炭 0
        )
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(FORGE_OBJECT_ID),
                "craft_ingots",
            )

    def test_excess_inventory_only_consumes_required_amount(self) -> None:
        """鉱石を 5 個持っていても、消費されるのは required_quantity の 2 個だけ。"""
        app, inventory_repo, item_repo = _build_app(
            initial_items=(ORE_SPEC_ID,) * 5 + (COAL_SPEC_ID, COAL_SPEC_ID),
        )
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(FORGE_OBJECT_ID),
            "craft_ingots",
        )
        counts = _counts(inventory_repo, item_repo)
        # 鉱石 5 → 3 残、石炭 2 → 1 残、インゴット 3 個
        assert counts.get(ORE_SPEC_ID) == 3
        assert counts.get(COAL_SPEC_ID) == 1
        assert counts.get(INGOT_SPEC_ID) == 3

    def test_count_helper_aggregates_all_slots(self) -> None:
        """count_owned_item_instances_by_spec が複数 instance を正しく合算する。"""
        _, inventory_repo, item_repo = _build_app(
            initial_items=(ORE_SPEC_ID, ORE_SPEC_ID, ORE_SPEC_ID, COAL_SPEC_ID),
        )
        counts = _counts(inventory_repo, item_repo)
        assert counts == {ORE_SPEC_ID: 3, COAL_SPEC_ID: 1}

    def test_count_helper_excludes_equipment_slots(self) -> None:
        """装備スロットのアイテムは「消費可能 count」に含めない (REMOVE と semantics 整合)。"""
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            count_owned_item_instances_by_spec,
        )
        from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        _, inventory_repo, item_repo = _build_app(
            initial_items=(ORE_SPEC_ID, ORE_SPEC_ID),
        )
        inv = inventory_repo.find_by_id(PlayerId(PLAYER_ID))
        # slot 0 の鉱石を装備スロット (例: WEAPON) に移す
        # （現実には鉱石は装備しないが、装備スロットが count から除外
        # されていることをテストするための人工状況）
        slot0_iid = inv.get_item_instance_id_by_slot(SlotId(0))
        assert slot0_iid is not None
        inv.drop_item(SlotId(0))
        inv._equipment_slots[EquipmentSlotType.WEAPON] = slot0_iid
        inventory_repo.save(inv)

        counts = count_owned_item_instances_by_spec(inv, item_repo)
        # 装備中の 1 個は除外され、bag に残る 1 個だけがカウントされる
        assert counts.get(ORE_SPEC_ID) == 1

    def test_remove_item_raises_when_count_insufficient_at_runtime(self) -> None:
        """precondition バリデーション後に REMOVE 対象が無い不整合は ApplicationException で明示する。

        通常 precondition で弾かれるため発生しないが、たとえば
        precondition と effect の quantity が一致しない作家ミスを早期検出
        するための invariant guard。ここでは effect の quantity を
        手動で precondition より大きくしたケースをシミュレートする。
        """
        from ai_rpg_world.application.common.exceptions import ApplicationException

        # 鉱石 1 個しか持たないプレイヤーで、precondition は緩い (required=1)
        # だが effect 側で 2 個 REMOVE しようとする scenario を直接構築する。
        forge_recipe = InteractionDef(
            action_name="bad_recipe",
            display_label="壊れたレシピ",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                    target_item_spec_id=ORE_SPEC_ID,
                    required_quantity=1,
                ),
            ),
            effects=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
                    parameters={"item_spec_id": ORE_SPEC_ID.value, "quantity": 2},
                ),
            ),
        )
        forge = SpotObject(
            object_id=SpotObjectId.create(FORGE_OBJECT_ID),
            name="forge", description="d",
            object_type=SpotObjectTypeEnum.OTHER,
            state={}, interactions=(forge_recipe,),
        )
        spot = SpotNode(
            spot_id=SpotId.create(SPOT_ID), name="smithy", description="d",
            category=SpotCategoryEnum.OTHER, parent_id=None,
        )
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        graph.add_spot(spot)
        graph.place_entity(EntityId.create(PLAYER_ID), SpotId.create(SPOT_ID))
        graph.clear_events()

        spot_graph_repo = InMemorySpotGraphRepository(graph)
        interior_repo = InMemorySpotInteriorRepository()
        interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (forge,), (), ()))
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        inventory_repo = InMemoryPlayerInventoryRepository(data_store)
        item_repo = InMemoryItemRepository(data_store)
        item_spec_repo = InMemoryItemSpecRepository()
        item_spec_repo.save(ItemSpecReadModel(
            item_spec_id=ORE_SPEC_ID, name="鉄鉱石",
            item_type=ItemType.MATERIAL, rarity=Rarity.COMMON,
            description="d", max_stack_size=MaxStackSize(99),
        ))
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(PLAYER_ID)))
        grant_item_specs_to_inventory(
            PlayerId(PLAYER_ID), (ORE_SPEC_ID,),  # 鉱石 1 個だけ
            item_repo, item_spec_repo, inventory_repo,
        )
        flags = MutableWorldFlagState()
        app = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=interior_repo,
            player_inventory_repository=inventory_repo,
            item_repository=item_repo,
            item_spec_repository=item_spec_repo,
            world_flag_state=flags,
            player_status_repository=status_repo,
        )
        with pytest.raises(ApplicationException, match="REMOVE_ITEM"):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(FORGE_OBJECT_ID),
                "bad_recipe",
            )
