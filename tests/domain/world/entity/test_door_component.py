"""DoorComponent の正常・例外ケースの網羅的テスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object_component import DoorComponent
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException


class TestDoorComponent:
    """DoorComponent のテスト"""

    class TestCreation:
        def test_default_creation(self):
            door = DoorComponent()
            assert door.is_open is False
            assert door.is_locked is False
            assert door.get_type_name() == "door"

        def test_creation_locked(self):
            door = DoorComponent(is_locked=True)
            assert door.is_locked is True
            assert door.is_open is False

        def test_creation_open(self):
            door = DoorComponent(is_open=True)
            assert door.is_open is True

    class TestInteractionType:
        def test_interaction_type_is_open_door(self):
            door = DoorComponent()
            assert door.interaction_type == InteractionTypeEnum.OPEN_DOOR

        def test_interaction_data(self):
            door = DoorComponent(is_open=True, is_locked=False)
            assert door.interaction_data == {"is_open": True, "is_locked": False}

        def test_interaction_duration(self):
            door = DoorComponent()
            assert door.interaction_duration == 1

    class TestOpenClose:
        def test_open_when_unlocked(self):
            door = DoorComponent(is_open=False, is_locked=False)
            door.open()
            assert door.is_open is True

        def test_open_raises_when_locked(self):
            door = DoorComponent(is_locked=True)
            with pytest.raises(LockedDoorException):
                door.open()

        def test_close(self):
            door = DoorComponent(is_open=True)
            door.close()
            assert door.is_open is False

        def test_toggle_open_when_unlocked(self):
            door = DoorComponent(is_open=False, is_locked=False)
            door.toggle_open()
            assert door.is_open is True
            door.toggle_open()
            assert door.is_open is False

        def test_toggle_open_raises_when_locked(self):
            door = DoorComponent(is_locked=True)
            with pytest.raises(LockedDoorException):
                door.toggle_open()

        def test_unlock_then_open(self):
            door = DoorComponent(is_locked=True)
            door.unlock()
            assert door.is_locked is False
            door.open()
            assert door.is_open is True

    class TestToDict:
        def test_to_dict(self):
            door = DoorComponent(is_open=True, is_locked=False)
            assert door.to_dict() == {"is_open": True, "is_locked": False}
