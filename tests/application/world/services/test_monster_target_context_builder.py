import unittest.mock as mock

from ai_rpg_world.application.world.services.monster_target_context_builder import (
    MonsterTargetContextBuilder,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestMonsterTargetContextBuilder:
    def test_returns_none_without_aggro_and_pack_leader(self):
        builder = MonsterTargetContextBuilder(
            monster_repository=mock.Mock(),
            aggro_store=None,
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(),
        )

        assert builder.build_target_context(actor, mock.Mock(), WorldTick(10)) is None

    def test_builds_target_context_from_aggro_store(self):
        aggro_store = mock.Mock(
            get_threat_by_attacker=mock.Mock(
                return_value={WorldObjectId(99): 10}
            )
        )
        builder = MonsterTargetContextBuilder(
            monster_repository=mock.Mock(),
            aggro_store=aggro_store,
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(),
        )
        physical_map = mock.Mock()
        physical_map.spot_id = mock.sentinel.spot_id

        context = builder.build_target_context(actor, physical_map, WorldTick(10))

        assert context is not None
        assert context.threat_by_id == {WorldObjectId(99): 10}

    def test_builds_target_context_with_pack_leader_target(self):
        leader = mock.Mock()
        leader.object_id = WorldObjectId(2)
        leader.component.is_pack_leader = True
        leader_monster = mock.Mock(behavior_target_id=WorldObjectId(88))
        monster_repository = mock.Mock(
            find_by_world_object_id=mock.Mock(return_value=leader_monster)
        )
        builder = MonsterTargetContextBuilder(
            monster_repository=monster_repository,
            aggro_store=None,
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(pack_id=10, is_pack_leader=False),
        )
        physical_map = mock.Mock(get_actors_in_pack=mock.Mock(return_value=[leader]))

        context = builder.build_target_context(actor, physical_map, WorldTick(10))

        assert context is not None
        assert context.pack_leader_target_id == WorldObjectId(88)
