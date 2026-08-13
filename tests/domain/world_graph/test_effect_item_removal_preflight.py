"""品目削除不足を、状態変更や抽選より前に拒否する契約を保証する。"""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InsufficientEffectItemsException,
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)


_ORE = ItemSpecId.create(41)


@dataclass
class _MutablePlayerState:
    """効果適用時に実際の辞書を書き換える最小のプレイヤー状態偽物。"""

    state: dict

    def merge_state(self, updates: dict) -> None:
        self.state.update(updates)


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


def _interaction(*effects: InteractionEffect) -> InteractionDef:
    return InteractionDef(
        action_name="test",
        display_label="試す",
        preconditions=(),
        effects=effects,
    )


def _remove_two() -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
        parameters={"item_spec_id": int(_ORE), "quantity": 2},
    )


def _item() -> ItemAggregate:
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId.create(91),
        item_spec=ItemSpec(
            item_spec_id=ItemSpecId.create(92),
            name="道具",
            item_type=ItemType.TOOL,
            rarity=Rarity.COMMON,
            description="試験用",
            max_stack_size=MaxStackSize(1),
        ),
        quantity=1,
        state={"used": False},
    )


class TestEffectItemRemovalPreflight:
    """削除要求の不足時に、後続効果が一切開始されないことを保証する。"""

    def test_item_state_is_unchanged_when_removal_is_insufficient(self) -> None:
        """道具状態変更より後にREMOVE_ITEMを書いても、不足時は状態を変えない。"""
        item = _item()
        change = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"used": True}},
        )

        with pytest.raises(InsufficientEffectItemsException):
            SpotInteractionService().execute_declared_interaction(
                _empty_interior(),
                _interaction(change, _remove_two()),
                frozenset({_ORE}),
                frozenset(),
                owned_item_spec_counts={_ORE: 1},
                acting_item_aggregate=item,
            )

        assert item.state == {"used": False}

    def test_player_state_is_unchanged_when_removal_is_insufficient(self) -> None:
        """プレイヤー状態変更より後にREMOVE_ITEMを書いても、不足時は状態を変えない。"""
        player = _MutablePlayerState(state={"mood": "calm"})
        change = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"mood": "afraid"}},
        )

        with pytest.raises(InsufficientEffectItemsException):
            SpotInteractionService().execute_declared_interaction(
                _empty_interior(),
                _interaction(change, _remove_two()),
                frozenset({_ORE}),
                frozenset(),
                owned_item_spec_counts={_ORE: 1},
                acting_player_status=player,
            )

        assert player.state == {"mood": "calm"}

    def test_loot_roll_is_not_started_when_removal_is_insufficient(self) -> None:
        """loot効果が先に宣言されていても、不足時は抽選元へ問い合わせない。"""
        loot_repository = Mock()
        effect_service = WorldGraphEffectService(
            loot_table_repository=loot_repository
        )
        loot = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE,
            parameters={"loot_table_id": 1},
        )

        with pytest.raises(InsufficientEffectItemsException):
            SpotInteractionService(effect_service=effect_service).execute_declared_interaction(
                _empty_interior(),
                _interaction(loot, _remove_two()),
                frozenset({_ORE}),
                frozenset(),
                owned_item_spec_counts={_ORE: 1},
            )

        loot_repository.find_by_id.assert_not_called()

    def test_deposit_without_counts_stops_before_player_state_change(self) -> None:
        """DEPOSITの所持数が未配線なら、先行する状態変更より前に停止する。"""
        player = _MutablePlayerState(state={"mood": "calm"})
        change = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"mood": "afraid"}},
        )
        deposit = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": int(_ORE),
                "state_key": "stored",
                "quantity": 1,
            },
        )

        with pytest.raises(
            InteractionEffectValidationException, match="所持数を必要とします"
        ):
            SpotInteractionService().execute_declared_interaction(
                _empty_interior(),
                _interaction(change, deposit),
                frozenset({_ORE}),
                frozenset(),
                acting_player_status=player,
            )

        assert player.state == {"mood": "calm"}

    def test_deposit_without_counts_stops_before_loot_roll(self) -> None:
        """DEPOSITの所持数が未配線なら、先行するloot抽選を開始しない。"""
        loot_repository = Mock()
        effect_service = WorldGraphEffectService(
            loot_table_repository=loot_repository
        )
        loot = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE,
            parameters={"loot_table_id": 1},
        )
        deposit = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": int(_ORE),
                "state_key": "stored",
                "quantity": 1,
            },
        )

        with pytest.raises(
            InteractionEffectValidationException, match="所持数を必要とします"
        ):
            SpotInteractionService(effect_service=effect_service).execute_declared_interaction(
                _empty_interior(),
                _interaction(loot, deposit),
                frozenset({_ORE}),
                frozenset(),
            )

        loot_repository.find_by_id.assert_not_called()
