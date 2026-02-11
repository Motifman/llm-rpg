import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxInactiveException
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import (
    ObstacleCollisionPolicy,
    TargetCollisionPolicy,
)
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect, HitEffectType
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestHitBoxAggregate:
    @pytest.fixture
    def hit_box_id(self) -> HitBoxId:
        return HitBoxId.create(1)

    @pytest.fixture
    def owner_id(self) -> WorldObjectId:
        return WorldObjectId.create(100)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(1)

    @pytest.fixture
    def shape(self) -> HitBoxShape:
        return HitBoxShape.single_cell()

    @pytest.fixture
    def aggregate(self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape) -> HitBoxAggregate:
        return HitBoxAggregate.create(
            hit_box_id=hit_box_id,
            spot_id=spot_id,
            owner_id=owner_id,
            shape=shape,
            initial_coordinate=Coordinate(5, 5, 0),
            start_tick=WorldTick(10),
            duration=5,
        )

    class TestCreate:
        def test_create_success(self, aggregate: HitBoxAggregate, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId):
            assert aggregate.hit_box_id == hit_box_id
            assert aggregate.spot_id == spot_id
            assert aggregate.owner_id == owner_id
            assert aggregate.current_coordinate == Coordinate(5, 5, 0)
            assert aggregate.is_active is True
            assert aggregate.power_multiplier == 1.0

            events = aggregate.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, HitBoxCreatedEvent)
            assert event.aggregate_id == hit_box_id
            assert event.aggregate_type == "HitBoxAggregate"
            assert event.spot_id == spot_id
            assert event.owner_id == owner_id
            assert event.initial_coordinate == Coordinate(5, 5, 0)
            assert event.duration == 5
            assert event.power_multiplier == 1.0
            assert event.shape_cell_count == 1
            assert event.effect_count == 0
            assert hasattr(event, "event_id")
            assert hasattr(event, "occurred_at")

        def test_create_invalid_duration_raises_exception(self, hit_box_id, spot_id, owner_id, shape):
            from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException
            with pytest.raises(HitBoxValidationException, match="duration must be greater than 0"):
                HitBoxAggregate.create(
                    hit_box_id=hit_box_id,
                    spot_id=spot_id,
                    owner_id=owner_id,
                    shape=shape,
                    initial_coordinate=Coordinate(0, 0, 0),
                    start_tick=WorldTick(0),
                    duration=0
                )

        def test_create_invalid_power_multiplier_raises_exception(self, hit_box_id, spot_id, owner_id, shape):
            from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException
            with pytest.raises(HitBoxValidationException, match="power_multiplier must be greater than 0"):
                HitBoxAggregate.create(
                    hit_box_id=hit_box_id,
                    spot_id=spot_id,
                    owner_id=owner_id,
                    shape=shape,
                    initial_coordinate=Coordinate(0, 0, 0),
                    start_tick=WorldTick(0),
                    duration=5,
                    power_multiplier=0.0
                )

        def test_create_with_hit_effects_sets_effect_count(self, hit_box_id, spot_id, owner_id, shape):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(0, 0, 0),
                start_tick=WorldTick(0),
                duration=3,
                hit_effects=[HitEffect.poison(2.0, duration_ticks=4), HitEffect.slow(0.3, duration_ticks=2)],
            )

            event = hit_box.get_events()[0]
            assert isinstance(event, HitBoxCreatedEvent)
            assert event.effect_count == 2
            assert len(hit_box.hit_effects) == 2
            assert hit_box.hit_effects[0].effect_type == HitEffectType.POISON

    class TestMovement:
        def test_move_to_success_adds_event(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()

            aggregate.move_to(Coordinate(6, 5, 0))

            assert aggregate.current_coordinate == Coordinate(6, 5, 0)
            events = aggregate.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, HitBoxMovedEvent)
            assert event.from_coordinate == Coordinate(5, 5, 0)
            assert event.to_coordinate == Coordinate(6, 5, 0)

        def test_move_to_same_coordinate_does_not_add_event(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()
            aggregate.move_to(Coordinate(5, 5, 0))
            assert aggregate.get_events() == []

        def test_move_to_inactive_raises_exception(self, aggregate: HitBoxAggregate):
            aggregate.deactivate()
            with pytest.raises(HitBoxInactiveException):
                aggregate.move_to(Coordinate(6, 6, 0))

        def test_on_tick_moves_with_velocity(self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(1, 1, 0),
                start_tick=WorldTick(0),
                duration=20,
                velocity=HitBoxVelocity(2, 0, 0),
            )
            hit_box.clear_events()

            hit_box.on_tick(WorldTick(1))

            assert hit_box.current_coordinate == Coordinate(3, 1, 0)
            moved_events = [e for e in hit_box.get_events() if isinstance(e, HitBoxMovedEvent)]
            assert len(moved_events) == 1

        def test_on_tick_stationary_hitbox_does_not_move(self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(1, 1, 0),
                start_tick=WorldTick(0),
                duration=20,
                velocity=HitBoxVelocity.zero(),
            )
            hit_box.clear_events()

            hit_box.on_tick(WorldTick(1))

            assert hit_box.current_coordinate == Coordinate(1, 1, 0)
            assert hit_box.get_events() == []

    class TestCoverage:
        def test_get_all_covered_coordinates_includes_path(self, shape: HitBoxShape):
            hit_box = HitBoxAggregate.create(
                hit_box_id=HitBoxId.create(2),
                spot_id=SpotId(1),
                owner_id=WorldObjectId.create(101),
                shape=shape,
                initial_coordinate=Coordinate(0, 0, 0),
                start_tick=WorldTick(0),
                duration=10,
            )

            hit_box.move_to(Coordinate(2, 0, 0))
            covered = hit_box.get_all_covered_coordinates()

            assert Coordinate(0, 0, 0) in covered
            assert Coordinate(1, 0, 0) in covered
            assert Coordinate(2, 0, 0) in covered

        def test_supercover_path_diagonal_movement(self, shape: HitBoxShape):
            # (0,0,0) -> (1,1,0) の斜め移動。Supercoverなら (1,0,0) や (0,1,0) も通る可能性がある
            hit_box = HitBoxAggregate.create(
                hit_box_id=HitBoxId.create(3),
                spot_id=SpotId(1),
                owner_id=WorldObjectId.create(102),
                shape=shape,
                initial_coordinate=Coordinate(0, 0, 0),
                start_tick=WorldTick(0),
                duration=10,
            )

            hit_box.move_to(Coordinate(1, 1, 0))
            covered = hit_box.get_all_covered_coordinates()

            # 始点と終点は必ず含まれる
            assert Coordinate(0, 0, 0) in covered
            assert Coordinate(1, 1, 0) in covered
            
            # Supercover なので、対角線上の移動で隣接するマスも含まれることを期待
            # (t_max の計算により、x軸境界かy軸境界のどちらかを先に踏むため)
            assert Coordinate(1, 0, 0) in covered or Coordinate(0, 1, 0) in covered

        def test_multi_cell_shape_coverage(self):
            # 十字型の HitBox が移動した場合の網羅テスト
            shape = HitBoxShape.cross()
            hit_box = HitBoxAggregate.create(
                hit_box_id=HitBoxId.create(4),
                spot_id=SpotId(1),
                owner_id=WorldObjectId.create(103),
                shape=shape,
                initial_coordinate=Coordinate(5, 5, 0),
                start_tick=WorldTick(0),
                duration=10,
            )

            # (5,5) -> (6,5) への移動
            hit_box.move_to(Coordinate(6, 5, 0))
            covered = hit_box.get_all_covered_coordinates()

            # 元の位置の全マスが含まれるべき
            for rel in shape.relative_coordinates:
                assert Coordinate(5 + rel.dx, 5 + rel.dy, 0 + rel.dz) in covered
            
            # 新しい位置の全マスが含まれるべき
            for rel in shape.relative_coordinates:
                assert Coordinate(6 + rel.dx, 5 + rel.dy, 0 + rel.dz) in covered

    class TestHitRecording:
        def test_record_hit_success_adds_event(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()
            target_id = WorldObjectId.create(200)

            aggregate.record_hit(target_id)

            assert aggregate.has_hit(target_id) is True
            events = aggregate.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, HitBoxHitRecordedEvent)
            assert event.owner_id == aggregate.owner_id
            assert event.target_id == target_id
            assert event.hit_coordinate == Coordinate(5, 5, 0)

        def test_record_hit_duplicate_does_not_add_second_event(self, aggregate: HitBoxAggregate):
            target_id = WorldObjectId.create(200)
            aggregate.record_hit(target_id)
            aggregate.record_hit(target_id)

            events = [e for e in aggregate.get_events() if isinstance(e, HitBoxHitRecordedEvent)]
            assert len(events) == 1

        def test_record_hit_owner_is_ignored(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()
            aggregate.record_hit(aggregate.owner_id)
            assert aggregate.has_hit(aggregate.owner_id) is False
            assert not any(isinstance(e, HitBoxHitRecordedEvent) for e in aggregate.get_events())

        def test_record_hit_inactive_raises_exception(self, aggregate: HitBoxAggregate):
            aggregate.deactivate()
            with pytest.raises(HitBoxInactiveException):
                aggregate.record_hit(WorldObjectId.create(200))

        def test_record_hit_deactivates_when_target_collision_policy_is_deactivate(
            self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape
        ):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(2, 2, 0),
                start_tick=WorldTick(0),
                duration=20,
                target_collision_policy=TargetCollisionPolicy.DEACTIVATE,
            )
            hit_box.clear_events()

            hit_box.record_hit(WorldObjectId.create(777))

            assert hit_box.is_active is False
            events = hit_box.get_events()
            assert isinstance(events[0], HitBoxHitRecordedEvent)
            assert isinstance(events[1], HitBoxDeactivatedEvent)
            assert events[1].reason == "target_collision"

    class TestObstacleCollision:
        def test_record_obstacle_collision_pass_through_keeps_active(
            self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape
        ):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(2, 2, 0),
                start_tick=WorldTick(0),
                duration=20,
                obstacle_collision_policy=ObstacleCollisionPolicy.PASS_THROUGH,
            )
            hit_box.clear_events()

            hit_box.record_obstacle_collision(Coordinate(3, 2, 0))

            assert hit_box.is_active is True
            events = hit_box.get_events()
            assert len(events) == 1
            assert isinstance(events[0], HitBoxObstacleCollidedEvent)
            assert events[0].obstacle_collision_policy == ObstacleCollisionPolicy.PASS_THROUGH.value

        def test_record_obstacle_collision_deactivate_turns_inactive(
            self, hit_box_id: HitBoxId, spot_id: SpotId, owner_id: WorldObjectId, shape: HitBoxShape
        ):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_id,
                spot_id=spot_id,
                owner_id=owner_id,
                shape=shape,
                initial_coordinate=Coordinate(2, 2, 0),
                start_tick=WorldTick(0),
                duration=20,
                obstacle_collision_policy=ObstacleCollisionPolicy.DEACTIVATE,
            )
            hit_box.clear_events()

            hit_box.record_obstacle_collision(Coordinate(3, 2, 0))

            assert hit_box.is_active is False
            events = hit_box.get_events()
            assert isinstance(events[0], HitBoxObstacleCollidedEvent)
            assert isinstance(events[1], HitBoxDeactivatedEvent)
            assert events[1].reason == "obstacle_collision"

        def test_record_obstacle_collision_inactive_raises_exception(self, aggregate: HitBoxAggregate):
            aggregate.deactivate()
            with pytest.raises(HitBoxInactiveException):
                aggregate.record_obstacle_collision(Coordinate(5, 6, 0))

    class TestLifecycle:
        def test_is_expired(self, aggregate: HitBoxAggregate):
            assert aggregate.is_expired(WorldTick(14)) is False
            assert aggregate.is_expired(WorldTick(15)) is True

        def test_deactivate_adds_event_once(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()
            aggregate.deactivate(reason="expired")
            aggregate.deactivate(reason="expired")

            assert aggregate.is_active is False
            events = aggregate.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, HitBoxDeactivatedEvent)
            assert event.reason == "expired"

        def test_on_tick_expired_deactivates_hit_box(self, aggregate: HitBoxAggregate):
            aggregate.clear_events()
            aggregate.on_tick(WorldTick(15))

            assert aggregate.is_active is False
            events = aggregate.get_events()
            assert len(events) == 1
            assert isinstance(events[0], HitBoxDeactivatedEvent)
            assert events[0].reason == "expired"
