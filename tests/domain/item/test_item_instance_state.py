"""Phase 4-A: ItemInstance / ItemAggregate の per-instance state テスト。

`state: Dict[str, Any]` を ItemInstance に追加することで、同 spec の
instance ごとに「lit/unlit、charges_remaining、enchantment_level」など
任意の状態を持たせられることを保証する。`SpotObject.state` と同じ
flat dict セマンティクス（部分マージ可能）を採用している。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize


def _spec(stack_size: int = 64, durability_max: int | None = None) -> ItemSpec:
    """state テスト用の最小 ItemSpec (durability ありなら EQUIPMENT、なければ MATERIAL)。"""
    if durability_max is not None:
        from ai_rpg_world.domain.item.enum.item_enum import EquipmentType

        return ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="Lantern",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A lantern.",
            max_stack_size=MaxStackSize(stack_size),
            durability_max=durability_max,
            equipment_type=EquipmentType.WEAPON,
        )
    return ItemSpec(
        item_spec_id=ItemSpecId(1),
        name="Lantern",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="A lantern.",
        max_stack_size=MaxStackSize(stack_size),
        durability_max=None,
    )


class TestItemInstanceState:
    """ItemInstance.state の基本挙動。"""

    def test_default_state_is_empty_dict(self) -> None:
        """state を渡さない場合、空辞書として初期化される。"""
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
        )
        assert inst.state == {}

    def test_state_initial_value_can_be_set(self) -> None:
        """初期 state を constructor で渡せる。"""
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"lit": True, "charges_remaining": 5},
        )
        assert inst.state == {"lit": True, "charges_remaining": 5}

    def test_state_property_returns_defensive_copy(self) -> None:
        """state プロパティは内部 dict の防御的コピーを返す（外部からの破壊不可）。"""
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"lit": True},
        )
        snapshot = inst.state
        # snapshot を破壊しても内部に影響しない
        snapshot["lit"] = False
        snapshot["foo"] = "bar"
        assert inst.state == {"lit": True}

    def test_replace_state_swaps_entire_dict(self) -> None:
        """replace_state は state 全体を置き換える。"""
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"a": 1, "b": 2},
        )
        inst.replace_state({"c": 3})
        # a, b は消える
        assert inst.state == {"c": 3}

    def test_merge_state_overwrites_keys_and_adds_new(self) -> None:
        """merge_state は同名キー上書き、新規キー追加（部分マージ）。"""
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"lit": True, "charges": 5},
        )
        inst.merge_state({"lit": False, "extra": "x"})
        assert inst.state == {"lit": False, "charges": 5, "extra": "x"}


class TestItemAggregateStateExposure:
    """ItemAggregate 経由で state にアクセス・変更できる。"""

    def test_create_with_initial_state(self) -> None:
        """`ItemAggregate.create(state=...)` で初期 state を指定できる。"""
        agg = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            quantity=1,
            state={"lit": False},
        )
        assert agg.state == {"lit": False}

    def test_aggregate_replace_state(self) -> None:
        """ItemAggregate.replace_state で内部 instance の state を置き換える。"""
        agg = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"a": 1},
        )
        agg.replace_state({"b": 2})
        assert agg.state == {"b": 2}

    def test_aggregate_merge_state(self) -> None:
        """ItemAggregate.merge_state は部分マージ。"""
        agg = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"a": 1},
        )
        agg.merge_state({"b": 2})
        assert agg.state == {"a": 1, "b": 2}

    def test_get_item_info_includes_state(self) -> None:
        """get_item_info DTO に state が含まれる（serialization 表面の一貫性）。"""
        agg = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=_spec(),
            state={"lit": True, "charges": 3},
        )
        info = agg.get_item_info()
        assert info["state"] == {"lit": True, "charges": 3}


class TestStackingForbidsStatefulInstances:
    """state を持つ instance はスタック対象外。"""

    def test_two_empty_state_instances_can_stack(self) -> None:
        """state が両方とも空ならスタック可能 (default 挙動を維持)。"""
        a = ItemInstance(item_instance_id=ItemInstanceId(1), item_spec=_spec())
        b = ItemInstance(item_instance_id=ItemInstanceId(2), item_spec=_spec())
        assert a.can_stack_with(b) is True

    def test_one_side_with_state_disallows_stacking(self) -> None:
        """片方が state を持つだけでもスタック不可（混じると state が失われる）。"""
        a = ItemInstance(
            item_instance_id=ItemInstanceId(1), item_spec=_spec(),
            state={"lit": True},
        )
        b = ItemInstance(item_instance_id=ItemInstanceId(2), item_spec=_spec())
        assert a.can_stack_with(b) is False
        assert b.can_stack_with(a) is False

    def test_both_with_state_disallows_stacking_even_when_equal(self) -> None:
        """同じ state でもスタック不可（量子化された個別 instance を保つ）。"""
        a = ItemInstance(
            item_instance_id=ItemInstanceId(1), item_spec=_spec(),
            state={"lit": True},
        )
        b = ItemInstance(
            item_instance_id=ItemInstanceId(2), item_spec=_spec(),
            state={"lit": True},
        )
        assert a.can_stack_with(b) is False


class TestStateValueTypeValidation:
    """state 値型は JSON プリミティブに制限される（永続化境界の早期 fail）。"""

    def test_non_primitive_value_in_constructor_rejected(self) -> None:
        """constructor 経由で datetime 等を入れると ItemInstanceStateValidationException。"""
        from datetime import datetime

        from ai_rpg_world.domain.item.exception import (
            ItemInstanceStateValidationException,
        )

        with pytest.raises(
            ItemInstanceStateValidationException, match="not JSON-serializable"
        ):
            ItemInstance(
                item_instance_id=ItemInstanceId(1),
                item_spec=_spec(),
                state={"created_at": datetime(2026, 1, 1)},
            )

    def test_non_primitive_value_in_replace_state_rejected(self) -> None:
        """replace_state でも検証されてエラーになる。"""
        from ai_rpg_world.domain.item.exception import (
            ItemInstanceStateValidationException,
        )

        inst = ItemInstance(item_instance_id=ItemInstanceId(1), item_spec=_spec())
        with pytest.raises(ItemInstanceStateValidationException):
            inst.replace_state({"obj": object()})

    def test_non_primitive_value_in_merge_state_rejected(self) -> None:
        """merge_state でも検証されてエラーになる。state は変化しない。"""
        from ai_rpg_world.domain.item.exception import (
            ItemInstanceStateValidationException,
        )

        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1), item_spec=_spec(),
            state={"lit": True},
        )
        with pytest.raises(ItemInstanceStateValidationException):
            inst.merge_state({"bad": [1, 2, 3]})  # list は非対応
        # 失敗時に state は元のまま (atomicity)
        assert inst.state == {"lit": True}

    def test_non_str_key_rejected(self) -> None:
        """state のキーは str のみ。int キー等は拒否。"""
        from ai_rpg_world.domain.item.exception import (
            ItemInstanceStateValidationException,
        )

        inst = ItemInstance(item_instance_id=ItemInstanceId(1), item_spec=_spec())
        with pytest.raises(ItemInstanceStateValidationException, match="state key must be str"):
            inst.merge_state({1: "a"})

    def test_all_primitive_types_accepted(self) -> None:
        """str / int / float / bool / None は全て通る。"""
        inst = ItemInstance(item_instance_id=ItemInstanceId(1), item_spec=_spec())
        inst.merge_state({
            "s": "x", "i": 42, "f": 1.5, "b": True, "n": None,
        })
        assert inst.state == {"s": "x", "i": 42, "f": 1.5, "b": True, "n": None}


class TestStateClearedReenablesStacking:
    """state を空にすればスタック対象に戻る (clearing 経路)。"""

    def test_replace_state_with_empty_dict_makes_stackable_again(self) -> None:
        """`replace_state({})` で state が空に戻れば、空 state 同士はスタック可能になる。"""
        a = ItemInstance(
            item_instance_id=ItemInstanceId(1), item_spec=_spec(),
            state={"lit": True},
        )
        b = ItemInstance(item_instance_id=ItemInstanceId(2), item_spec=_spec())
        # state あり → スタック不可
        assert a.can_stack_with(b) is False
        # state を空に戻す
        a.replace_state({})
        # 両方とも空 state なのでスタック可能
        assert a.can_stack_with(b) is True


class TestStateWithDurabilityCoexistence:
    """state と durability は独立して併存できる。"""

    def test_durable_instance_can_have_state(self) -> None:
        """durability_max を持つ spec の instance に state も設定可能。"""
        spec = _spec(stack_size=1, durability_max=100)
        inst = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=spec,
            durability=Durability(current=80, max_value=100),
            state={"enchantment": "fire"},
        )
        assert inst.state == {"enchantment": "fire"}
        assert inst.durability.current == 80
