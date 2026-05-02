import pytest

from ai_rpg_world.domain.player.exception import SpotNavigationStateInvalidException
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


def test_at_rest_and_sub_location() -> None:
    s = PlayerSpotNavigationState.at_rest(SpotId.create(1), SubLocationId.create(1))
    assert not s.is_traveling
    assert s.current_spot_id == SpotId.create(1)
    assert s.current_sub_location_id == SubLocationId.create(1)
    s2 = s.with_sub_location(None)
    assert s2.current_sub_location_id is None


def test_begin_travel_one_leg_two_ticks() -> None:
    t = PlayerSpotNavigationState.begin_travel(
        route=(SpotId.create(1), SpotId.create(2)),
        leg_connection_ids=(ConnectionId.create(10),),
        leg_travel_ticks=(2,),
    )
    assert t.is_traveling
    assert t.ticks_remaining_on_current_leg == 2

    c0, t1 = t.advance_one_world_tick()
    assert c0 == ()
    assert t1.ticks_remaining_on_current_leg == 1

    c1, t2 = t1.advance_one_world_tick()
    assert len(c1) == 1
    assert c1[0][0] == ConnectionId.create(10)
    assert c1[0][1] == SpotId.create(2)
    assert not t2.is_traveling
    assert t2.current_spot_id == SpotId.create(2)


def test_zero_tick_legs_chain_same_tick() -> None:
    t = PlayerSpotNavigationState.begin_travel(
        route=(SpotId.create(1), SpotId.create(2), SpotId.create(3)),
        leg_connection_ids=(ConnectionId.create(1), ConnectionId.create(2)),
        leg_travel_ticks=(0, 0),
    )
    c, end = t.advance_one_world_tick()
    assert len(c) == 2
    assert not end.is_traveling
    assert end.current_spot_id == SpotId.create(3)


def test_with_sub_location_while_traveling_raises() -> None:
    t = PlayerSpotNavigationState.begin_travel(
        route=(SpotId.create(1), SpotId.create(2)),
        leg_connection_ids=(ConnectionId.create(1),),
        leg_travel_ticks=(1,),
    )
    with pytest.raises(SpotNavigationStateInvalidException):
        t.with_sub_location(SubLocationId.create(1))
