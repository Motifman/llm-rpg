import pytest
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.map_trigger import DamageTrigger


class TestAreaTrigger:
    def test_creation(self):
        trigger_id = AreaTriggerId(1)
        area = RectArea(0, 2, 0, 2, 0, 0)
        effect = DamageTrigger(10)
        
        at = AreaTrigger(trigger_id, area, effect, "Trap")
        
        assert at.trigger_id == trigger_id
        assert at.area == area
        assert at.trigger == effect
        assert at.name == "Trap"
        assert at.is_active is True

    def test_contains(self):
        at = AreaTrigger(
            AreaTriggerId(1), 
            RectArea(0, 2, 0, 2, 0, 0), 
            DamageTrigger(10)
        )
        
        assert at.contains(Coordinate(1, 1, 0)) is True
        assert at.contains(Coordinate(3, 1, 0)) is False
        
        at.set_active(False)
        assert at.contains(Coordinate(1, 1, 0)) is False
