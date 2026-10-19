import pytest

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.event.combat_events import HitBoxDeactivatedEvent, HitBoxMovedEvent
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestHitBoxActivation:
    @pytest.mark.parametrize(
        ("velocity", "activation_coordinate", "final_coordinate", "movement_event_types"),
        [
            (HitBoxVelocity(0, 0), Coordinate(0, 0, 0), Coordinate(0, 0, 0), []),
            (HitBoxVelocity(1, 0), Coordinate(1, 0, 0), Coordinate(2, 0, 0), [HitBoxMovedEvent]),
        ],
        ids=["stationary", "moving"],
    )
    def test_activation_delay(self, velocity, activation_coordinate, final_coordinate, movement_event_types):
        """静止・移動の両方で発動前は動かず、発動時刻から寿命の直前までだけ移動を許す。"""
        start_tick = WorldTick(10)
        activation_tick = 20
        duration = 10
        
        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=start_tick,
            duration=duration,
            power_multiplier=1.0,
            velocity=velocity,
            activation_tick=activation_tick
        )
        hit_box.clear_events()
        
        # 活性化前 (Tick 15)
        hit_box.on_tick(WorldTick(15))
        assert hit_box.is_activated(WorldTick(15)) is False
        assert hit_box.is_active is True
        assert hit_box.current_coordinate == Coordinate(0, 0, 0)
        assert hit_box.get_events() == []
        
        # 活性化直前 (Tick 19)
        hit_box.on_tick(WorldTick(19))
        assert hit_box.is_activated(WorldTick(19)) is False
        assert hit_box.is_active is True
        assert hit_box.current_coordinate == Coordinate(0, 0, 0)
        assert hit_box.get_events() == []
        
        # 活性化 (Tick 20)
        hit_box.on_tick(WorldTick(20))
        assert hit_box.is_activated(WorldTick(20)) is True
        assert hit_box.is_active is True
        assert hit_box.current_coordinate == activation_coordinate
        assert [type(event) for event in hit_box.get_events()] == movement_event_types
        hit_box.clear_events()
        
        # 終了直前 (Tick 29)
        hit_box.on_tick(WorldTick(29))
        assert hit_box.is_active is True
        assert hit_box.current_coordinate == final_coordinate
        assert [type(event) for event in hit_box.get_events()] == movement_event_types
        hit_box.clear_events()
        
        # 終了 (Tick 30)
        hit_box.on_tick(WorldTick(30))
        assert hit_box.is_active is False
        assert hit_box.current_coordinate == final_coordinate
        events = hit_box.get_events()
        assert len(events) == 1
        assert isinstance(events[0], HitBoxDeactivatedEvent)
        assert events[0].reason == "expired"

    def test_invalid_activation_tick_raises_error(self):
        from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException
        
        with pytest.raises(HitBoxValidationException, match="activation_tick .* cannot be earlier than start_tick"):
            HitBoxAggregate.create(
                hit_box_id=HitBoxId(1),
                spot_id=SpotId(1),
                owner_id=WorldObjectId(100),
                shape=HitBoxShape.single_cell(),
                initial_coordinate=Coordinate(0, 0, 0),
                start_tick=WorldTick(10),
                duration=10,
                activation_tick=5 # start_tick(10)より前
            )
