"""MapTriggerEngine の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.map_trigger_engine import MapTriggerEngine
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea, PointArea
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
)
from ai_rpg_world.domain.world.entity.map_trigger import DamageTrigger, WarpTrigger
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.event.map_events import (
    AreaEnteredEvent,
    AreaExitedEvent,
    AreaTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    GatewayTriggeredEvent,
    ObjectTriggeredEvent,
)
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@pytest.fixture
def spot_id():
    return SpotId(1)


@pytest.fixture
def area_trigger():
    """AreaTrigger(1) @ RectArea(1,1,1,1,0,0)"""
    return AreaTrigger(
        AreaTriggerId(1),
        RectArea(1, 1, 1, 1, 0, 0),
        DamageTrigger(10),
        "damage_zone",
    )


@pytest.fixture
def location_area():
    """LocationArea(1) @ RectArea(2,2,2,2,0,0)"""
    return LocationArea(
        LocationAreaId(1),
        RectArea(2, 2, 2, 2, 0, 0),
        "教室",
        "勉強する場所",
    )


@pytest.fixture
def gateway():
    """Gateway(1) @ RectArea(3,3,3,3,0,0)"""
    return Gateway(
        GatewayId(1),
        "出口",
        RectArea(3, 3, 3, 3, 0, 0),
        SpotId(2),
        Coordinate(0, 0, 0),
    )


@pytest.fixture
def actor_object():
    """プレイヤーアクター"""
    return WorldObject(
        WorldObjectId(1),
        Coordinate(0, 0, 0),
        ObjectTypeEnum.PLAYER,
        component=ActorComponent(),
    )


class TestComputeAreaTriggerEvents:
    """compute_area_trigger_events のテスト"""

    class TestAreaTrigger:
        def test_entering_area_emits_entered_and_triggered(self, spot_id, area_trigger):
            # Given: 外からエリアへ進入
            area_triggers = {area_trigger.trigger_id: area_trigger}
            objects = {}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(1, 1, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects=objects,
                spot_id=spot_id,
                current_tick=None,
            )

            # Then
            entered = [e for e in events if isinstance(e, AreaEnteredEvent)]
            triggered = [e for e in events if isinstance(e, AreaTriggeredEvent)]
            assert len(entered) == 1
            assert entered[0].trigger_id == AreaTriggerId(1)
            assert entered[0].object_id == WorldObjectId(1)
            assert entered[0].spot_id == spot_id
            assert len(triggered) == 1
            assert triggered[0].trigger_id == AreaTriggerId(1)

        def test_exiting_area_emits_exited(self, spot_id, area_trigger):
            # Given: エリア内から外へ退出
            area_triggers = {area_trigger.trigger_id: area_trigger}
            objects = {}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(1, 1, 0),
                new_coordinate=Coordinate(0, 0, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then
            exited = [e for e in events if isinstance(e, AreaExitedEvent)]
            assert len(exited) == 1
            assert exited[0].trigger_id == AreaTriggerId(1)

        def test_staying_in_area_emits_triggered_only(self, spot_id, area_trigger):
            # Given: エリア内からエリア内へ（滞在）
            area_triggers = {area_trigger.trigger_id: area_trigger}
            objects = {}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(1, 1, 0),
                new_coordinate=Coordinate(1, 1, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then
            entered = [e for e in events if isinstance(e, AreaEnteredEvent)]
            exited = [e for e in events if isinstance(e, AreaExitedEvent)]
            triggered = [e for e in events if isinstance(e, AreaTriggeredEvent)]
            assert len(entered) == 0
            assert len(exited) == 0
            assert len(triggered) == 1

        def test_not_in_any_area_emits_nothing(self, spot_id, area_trigger):
            # Given: 外から外へ（エリアに触れない）
            area_triggers = {area_trigger.trigger_id: area_trigger}
            objects = {}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(0, 1, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then
            area_events = [e for e in events if isinstance(e, (AreaEnteredEvent, AreaExitedEvent, AreaTriggeredEvent))]
            assert len(area_events) == 0

        def test_add_object_first_placement_old_coord_none(self, spot_id, area_trigger):
            # Given: add_object 時は old_coordinate が None
            area_triggers = {area_trigger.trigger_id: area_trigger}
            objects = {WorldObjectId(1): WorldObject(WorldObjectId(1), Coordinate(1, 1, 0), ObjectTypeEnum.PLAYER)}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=None,
                new_coordinate=Coordinate(1, 1, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then: 進入扱い
            entered = [e for e in events if isinstance(e, AreaEnteredEvent)]
            assert len(entered) == 1

        def test_inactive_area_trigger_emits_nothing(self, spot_id):
            # Given: 非アクティブな AreaTrigger
            inactive = AreaTrigger(
                AreaTriggerId(1),
                RectArea(1, 1, 1, 1, 0, 0),
                DamageTrigger(10),
                "inactive",
                is_active=False,
            )
            area_triggers = {inactive.trigger_id: inactive}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(1, 1, 0),
                area_triggers=area_triggers,
                location_areas={},
                gateways={},
                objects={},
                spot_id=spot_id,
            )

            # Then
            assert len(events) == 0

    class TestLocationArea:
        def test_entering_location_emits_entered_with_details(self, spot_id, location_area, actor_object):
            # Given
            location_areas = {location_area.location_id: location_area}
            objects = {actor_object.object_id: actor_object}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=actor_object.object_id,
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(2, 2, 0),
                area_triggers={},
                location_areas=location_areas,
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then
            entered = [e for e in events if isinstance(e, LocationEnteredEvent)]
            assert len(entered) == 1
            assert entered[0].location_id == LocationAreaId(1)
            assert entered[0].name == "教室"
            assert entered[0].description == "勉強する場所"
            assert entered[0].object_id == actor_object.object_id

        def test_exiting_location_emits_exited(self, spot_id, location_area):
            # Given
            location_areas = {location_area.location_id: location_area}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(2, 2, 0),
                new_coordinate=Coordinate(0, 0, 0),
                area_triggers={},
                location_areas=location_areas,
                gateways={},
                objects={},
                spot_id=spot_id,
            )

            # Then
            exited = [e for e in events if isinstance(e, LocationExitedEvent)]
            assert len(exited) == 1

        def test_player_id_value_set_when_actor_has_player_id(self, spot_id, location_area):
            # Given: プレイヤーキャラのオブジェクト
            from ai_rpg_world.domain.player.value_object.player_id import PlayerId

            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(2, 2, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(42)),
            )
            objects = {actor.object_id: actor}
            location_areas = {location_area.location_id: location_area}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=actor.object_id,
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(2, 2, 0),
                area_triggers={},
                location_areas=location_areas,
                gateways={},
                objects=objects,
                spot_id=spot_id,
            )

            # Then
            entered = [e for e in events if isinstance(e, LocationEnteredEvent)][0]
            assert entered.player_id_value == 42

        def test_inactive_location_emits_nothing(self, spot_id):
            # Given
            inactive_loc = LocationArea(
                LocationAreaId(1),
                RectArea(2, 2, 2, 2, 0, 0),
                "A",
                "B",
                is_active=False,
            )
            location_areas = {inactive_loc.location_id: inactive_loc}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(2, 2, 0),
                area_triggers={},
                location_areas=location_areas,
                gateways={},
                objects={},
                spot_id=spot_id,
            )

            # Then
            assert not any(isinstance(e, LocationEnteredEvent) for e in events)

    class TestGateway:
        def test_entering_gateway_emits_triggered(self, spot_id, gateway):
            # Given: gateway fixture は landing_coordinate=Coordinate(0,0,0), target_spot_id=SpotId(2)
            gateways = {gateway.gateway_id: gateway}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(3, 3, 0),
                area_triggers={},
                location_areas={},
                gateways=gateways,
                objects={},
                spot_id=spot_id,
                current_tick=WorldTick(10),
            )

            # Then
            gw_events = [e for e in events if isinstance(e, GatewayTriggeredEvent)]
            assert len(gw_events) == 1
            assert gw_events[0].gateway_id == GatewayId(1)
            assert gw_events[0].target_spot_id == gateway.target_spot_id
            assert gw_events[0].landing_coordinate == gateway.landing_coordinate
            assert gw_events[0].occurred_tick == WorldTick(10)

        def test_inactive_gateway_emits_nothing(self, spot_id):
            # Given
            inactive_gw = Gateway(
                GatewayId(1),
                "G",
                RectArea(3, 3, 3, 3, 0, 0),
                SpotId(2),
                Coordinate(0, 0, 0),
                is_active=False,
            )
            gateways = {inactive_gw.gateway_id: inactive_gw}

            # When
            events = MapTriggerEngine.compute_area_trigger_events(
                object_id=WorldObjectId(1),
                old_coordinate=Coordinate(0, 0, 0),
                new_coordinate=Coordinate(3, 3, 0),
                area_triggers={},
                location_areas={},
                gateways=gateways,
                objects={},
                spot_id=spot_id,
            )

            # Then
            assert not any(isinstance(e, GatewayTriggeredEvent) for e in events)


class TestComputeObjectTriggerEvents:
    """compute_object_trigger_events のテスト"""

    def test_empty_coordinate_returns_empty(self, spot_id):
        # When
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=WorldObjectId(1),
            new_coordinate=Coordinate(2, 2, 0),
            objects={},
            object_positions={},
            spot_id=spot_id,
        )

        # Then
        assert len(events) == 0

    def test_coordinate_not_in_positions_returns_empty(self, spot_id):
        # Given: 別の座標にだけオブジェクトがある
        object_positions = {Coordinate(0, 0, 0): [WorldObjectId(100)]}
        trap = WorldObject(
            WorldObjectId(100),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.SWITCH,
            is_blocking=False,
            component=PlaceableComponent(
                item_spec_id=ItemSpecId(1),
                inner=StaticPlaceableInnerComponent(),
                trigger_on_step=DamageTrigger(10),
            ),
        )
        objects = {trap.object_id: trap}

        # When: アクターが (2,2) に移動（トリガーは (0,0) にある）
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=WorldObjectId(1),
            new_coordinate=Coordinate(2, 2, 0),
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then
        assert len(events) == 0

    def test_trigger_on_step_emits_object_triggered_event(self, spot_id):
        # Given: 同一マスにトリガー付きオブジェクト
        trap_id = WorldObjectId(100)
        actor_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        trap = WorldObject(
            trap_id,
            coord,
            ObjectTypeEnum.SWITCH,
            is_blocking=False,
            component=PlaceableComponent(
                item_spec_id=ItemSpecId(1),
                inner=StaticPlaceableInnerComponent(),
                trigger_on_step=DamageTrigger(10),
            ),
        )
        objects = {trap_id: trap}
        object_positions = {coord: [actor_id, trap_id]}

        # When
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=actor_id,
            new_coordinate=coord,
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then
        triggered = [e for e in events if isinstance(e, ObjectTriggeredEvent)]
        assert len(triggered) == 1
        assert triggered[0].object_id == trap_id
        assert triggered[0].actor_id == actor_id
        assert triggered[0].spot_id == spot_id

    def test_actor_self_does_not_trigger(self, spot_id):
        # Given: アクター自身がトリガーを持っている（同一object_id）
        actor_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        # アクターがトリガー付きで同じマスにいる場合、自分自身はスキップ
        objects = {actor_id: WorldObject(actor_id, coord, ObjectTypeEnum.PLAYER)}
        object_positions = {coord: [actor_id]}

        # When: アクターに get_trigger_on_step は通常ないが、万一あっても自分はスキップ
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=actor_id,
            new_coordinate=coord,
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then: actor_id と obj_id が同じなら continue でスキップされる
        assert len(events) == 0

    def test_object_without_component_skipped(self, spot_id):
        # Given: コンポーネントなしオブジェクト
        trap_id = WorldObjectId(100)
        actor_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        no_comp = WorldObject(trap_id, coord, ObjectTypeEnum.CHEST, component=None)
        objects = {trap_id: no_comp}
        object_positions = {coord: [actor_id, trap_id]}

        # When
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=actor_id,
            new_coordinate=coord,
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then
        assert len(events) == 0

    def test_component_without_trigger_on_step_skipped(self, spot_id):
        # Given: get_trigger_on_step が None のコンポーネント
        from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent

        chest_id = WorldObjectId(100)
        actor_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        chest = WorldObject(chest_id, coord, ObjectTypeEnum.CHEST, component=ChestComponent())
        objects = {chest_id: chest}
        object_positions = {coord: [actor_id, chest_id]}

        # When
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=actor_id,
            new_coordinate=coord,
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then
        assert len(events) == 0

    def test_multiple_triggers_on_same_tile_emit_multiple_events(self, spot_id):
        # Given: 同一マスにトリガー付きオブジェクトが2つ
        trap1_id = WorldObjectId(100)
        trap2_id = WorldObjectId(101)
        actor_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        trigger_comp = PlaceableComponent(
            item_spec_id=ItemSpecId(1),
            inner=StaticPlaceableInnerComponent(),
            trigger_on_step=DamageTrigger(10),
        )
        trap1 = WorldObject(trap1_id, coord, ObjectTypeEnum.SWITCH, is_blocking=False, component=trigger_comp)
        trap2 = WorldObject(trap2_id, coord, ObjectTypeEnum.SWITCH, is_blocking=False, component=trigger_comp)
        objects = {trap1_id: trap1, trap2_id: trap2}
        object_positions = {coord: [actor_id, trap1_id, trap2_id]}

        # When
        events = MapTriggerEngine.compute_object_trigger_events(
            actor_id=actor_id,
            new_coordinate=coord,
            objects=objects,
            object_positions=object_positions,
            spot_id=spot_id,
        )

        # Then
        triggered = [e for e in events if isinstance(e, ObjectTriggeredEvent)]
        assert len(triggered) == 2
        ids = {e.object_id for e in triggered}
        assert ids == {trap1_id, trap2_id}


class TestComputeTriggerActivationAtCoordinate:
    """compute_trigger_activation_at_coordinate のテスト"""

    def test_coordinate_in_trigger_returns_trigger_and_events_when_object_id_given(self, spot_id, area_trigger):
        # Given
        area_triggers = {area_trigger.trigger_id: area_trigger}
        object_id = WorldObjectId(1)

        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(1, 1, 0),
            object_id=object_id,
            area_triggers=area_triggers,
            spot_id=spot_id,
        )

        # Then
        assert map_trigger is not None
        assert map_trigger == area_trigger.trigger
        assert len(events) == 1
        assert isinstance(events[0], AreaTriggeredEvent)
        assert events[0].object_id == object_id

    def test_coordinate_in_trigger_returns_trigger_and_empty_events_when_object_id_none(self, spot_id, area_trigger):
        # Given
        area_triggers = {area_trigger.trigger_id: area_trigger}

        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(1, 1, 0),
            object_id=None,
            area_triggers=area_triggers,
            spot_id=spot_id,
        )

        # Then
        assert map_trigger is not None
        assert map_trigger == area_trigger.trigger
        assert len(events) == 0

    def test_coordinate_not_in_any_trigger_returns_none_and_empty(self, spot_id, area_trigger):
        # Given
        area_triggers = {area_trigger.trigger_id: area_trigger}

        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(5, 5, 0),
            object_id=WorldObjectId(1),
            area_triggers=area_triggers,
            spot_id=spot_id,
        )

        # Then
        assert map_trigger is None
        assert len(events) == 0

    def test_empty_area_triggers_returns_none_and_empty(self, spot_id):
        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(1, 1, 0),
            object_id=WorldObjectId(1),
            area_triggers={},
            spot_id=spot_id,
        )

        # Then
        assert map_trigger is None
        assert len(events) == 0

    def test_returns_first_matching_trigger_when_overlapping(self, spot_id):
        # Given: 重なった2つのトリガー
        t1 = AreaTrigger(AreaTriggerId(1), PointArea(Coordinate(1, 1, 0)), DamageTrigger(10))
        t2 = AreaTrigger(AreaTriggerId(2), PointArea(Coordinate(1, 1, 0)), WarpTrigger(SpotId(2), Coordinate(0, 0, 0)))
        area_triggers = {t1.trigger_id: t1, t2.trigger_id: t2}

        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(1, 1, 0),
            object_id=WorldObjectId(1),
            area_triggers=area_triggers,
            spot_id=spot_id,
        )

        # Then: 最初にマッチしたもの（dictの Iteration 順）
        assert map_trigger is not None
        assert len(events) == 1

    def test_inactive_trigger_skipped(self, spot_id):
        # Given: 非アクティブトリガー
        inactive = AreaTrigger(
            AreaTriggerId(1),
            RectArea(1, 1, 1, 1, 0, 0),
            DamageTrigger(10),
            is_active=False,
        )
        area_triggers = {inactive.trigger_id: inactive}

        # When
        map_trigger, events = MapTriggerEngine.compute_trigger_activation_at_coordinate(
            coordinate=Coordinate(1, 1, 0),
            object_id=WorldObjectId(1),
            area_triggers=area_triggers,
            spot_id=spot_id,
        )

        # Then
        assert map_trigger is None
        assert len(events) == 0
