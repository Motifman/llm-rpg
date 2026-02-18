"""ChestComponent の正常・例外ケースの網羅的テスト"""

import pytest
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import ItemAlreadyInChestException
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


class TestChestComponent:
    """ChestComponent のテスト"""

    class TestCreation:
        def test_default_creation(self):
            chest = ChestComponent()
            assert chest.is_open is False
            assert chest.item_ids == []
            assert chest.get_type_name() == "chest"

        def test_creation_with_item_ids(self):
            ids = [ItemInstanceId.create(1), ItemInstanceId.create(2)]
            chest = ChestComponent(is_open=True, item_ids=ids)
            assert chest.is_open is True
            assert chest.item_ids == ids
            assert [e.value for e in chest.item_ids] == [1, 2]

        def test_creation_empty_item_ids_default(self):
            chest = ChestComponent(is_open=False)
            assert chest.item_ids == []

    class TestInteractionType:
        def test_interaction_type_is_open_chest(self):
            chest = ChestComponent()
            assert chest.interaction_type == InteractionTypeEnum.OPEN_CHEST

        def test_interaction_data_contains_is_open(self):
            chest = ChestComponent(is_open=True)
            assert chest.interaction_data == {"is_open": True}
            chest.close()
            assert chest.interaction_data == {"is_open": False}

        def test_interaction_duration(self):
            chest = ChestComponent()
            assert chest.interaction_duration == 1

    class TestOpenClose:
        def test_open_and_close(self):
            chest = ChestComponent(is_open=False)
            chest.open()
            assert chest.is_open is True
            chest.close()
            assert chest.is_open is False

        def test_toggle_open_closed_to_open(self):
            chest = ChestComponent(is_open=False)
            chest.toggle_open()
            assert chest.is_open is True

        def test_toggle_open_open_to_closed(self):
            chest = ChestComponent(is_open=True)
            chest.toggle_open()
            assert chest.is_open is False

    class TestApplyInteractionFrom:
        """apply_interaction_from の正常ケース（効果のカプセル化）"""

        def test_apply_interaction_from_toggles_open_state(self):
            chest = ChestComponent(is_open=False)
            map_aggregate = MagicMock()
            chest.apply_interaction_from(
                WorldObjectId(1), WorldObjectId(2), map_aggregate, WorldTick(10)
            )
            assert chest.is_open is True
            map_aggregate.get_object.assert_not_called()
            map_aggregate.add_event.assert_not_called()

        def test_apply_interaction_from_open_to_closed(self):
            chest = ChestComponent(is_open=True)
            map_aggregate = MagicMock()
            chest.apply_interaction_from(
                WorldObjectId(1), WorldObjectId(2), map_aggregate, WorldTick(10)
            )
            assert chest.is_open is False

    class TestAddRemoveItem:
        def test_add_item(self):
            chest = ChestComponent()
            iid = ItemInstanceId.create(100)
            chest.add_item(iid)
            assert chest.item_ids == [iid]
            assert chest.has_item(iid) is True

        def test_add_multiple_items(self):
            chest = ChestComponent()
            a, b = ItemInstanceId.create(1), ItemInstanceId.create(2)
            chest.add_item(a)
            chest.add_item(b)
            assert len(chest.item_ids) == 2
            assert chest.has_item(a) and chest.has_item(b)

        def test_remove_item_returns_true_when_found(self):
            chest = ChestComponent()
            iid = ItemInstanceId.create(50)
            chest.add_item(iid)
            assert chest.remove_item(iid) is True
            assert chest.item_ids == []
            assert chest.has_item(iid) is False

        def test_remove_item_returns_false_when_not_found(self):
            chest = ChestComponent(item_ids=[ItemInstanceId.create(1)])
            not_present = ItemInstanceId.create(999)
            assert chest.remove_item(not_present) is False
            assert len(chest.item_ids) == 1

        def test_add_item_raises_when_already_in_chest(self):
            """同じ ItemInstanceId が既にチェストにある場合 ItemAlreadyInChestException"""
            chest = ChestComponent()
            iid = ItemInstanceId.create(100)
            chest.add_item(iid)
            with pytest.raises(ItemAlreadyInChestException):
                chest.add_item(iid)

        def test_remove_item_removes_item_and_leaves_others(self):
            """remove_item で指定したアイテムのみ削除され他は残る"""
            a, b = ItemInstanceId.create(7), ItemInstanceId.create(8)
            chest = ChestComponent(item_ids=[a, b])
            assert chest.remove_item(a) is True
            assert chest.has_item(a) is False
            assert chest.has_item(b) is True
            assert chest.item_ids == [b]

    class TestToDict:
        def test_to_dict_contains_is_open_and_item_ids(self):
            chest = ChestComponent(is_open=True, item_ids=[ItemInstanceId.create(1)])
            d = chest.to_dict()
            assert d["is_open"] is True
            assert d["item_ids"] == [1]

        def test_to_dict_empty_items(self):
            chest = ChestComponent()
            assert chest.to_dict() == {"is_open": False, "item_ids": []}
