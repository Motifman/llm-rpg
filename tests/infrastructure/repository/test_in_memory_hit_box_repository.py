from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import InMemoryHitBoxRepository


class TestInMemoryHitBoxRepository:
    def test_find_by_spot_id_returns_only_target_spot(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemoryHitBoxRepository(data_store=data_store)

        hb1 = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(0),
            duration=5,
        )
        hb2 = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(2),
            spot_id=SpotId(2),
            owner_id=WorldObjectId.create(101),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(0),
            duration=5,
        )
        repo.save(hb1)
        repo.save(hb2)

        result = repo.find_by_spot_id(SpotId(1))
        assert len(result) == 1
        assert result[0].hit_box_id == HitBoxId.create(1)

    def test_find_active_by_spot_id_excludes_inactive(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        repo = InMemoryHitBoxRepository(data_store=data_store)

        active = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(0),
            duration=5,
        )
        inactive = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(2),
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(101),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(1, 0, 0),
            start_tick=WorldTick(0),
            duration=5,
        )
        inactive.deactivate()
        repo.save(active)
        repo.save(inactive)

        result = repo.find_active_by_spot_id(SpotId(1))
        assert len(result) == 1
        assert result[0].hit_box_id == HitBoxId.create(1)
