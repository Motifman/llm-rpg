import pytest
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId

class TestSkillExecutionDomainService:
    @pytest.fixture
    def setup(self):
        targeting_service = SkillTargetingDomainService()
        to_hitbox_service = SkillToHitBoxDomainService()
        service = SkillExecutionDomainService(targeting_service, to_hitbox_service)
        
        # 共通の準備
        player_id = PlayerId(100)
        status = PlayerStatusAggregate(
            player_id=player_id,
            base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor.for_level(1),
            exp_table=ExpTable(100, 2.0),
            growth=Growth(1, 0, ExpTable(100, 2.0)),
            gold=Gold(0),
            hp=Hp.create(100, 100),
            mp=Mp.create(100, 100),
            stamina=Stamina.create(100, 100)
        )
        
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id.value, 10, 10)
        
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.road()) for x in range(10) for y in range(10)]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=player_id)
        )
        pmap.add_object(actor)
        
        skill_spec = SkillSpec(
            skill_id=SkillId(1),
            name="Test Skill",
            element=None,
            deck_cost=1,
            cast_lock_ticks=1,
            cooldown_ticks=10,
            power_multiplier=1.0,
            hit_pattern=SkillHitPattern.single_pulse(None, HitBoxShape.single_cell()),
            mp_cost=10
        )
        loadout.equip_skill(DeckTier.NORMAL, 0, skill_spec)
        
        return service, pmap, status, loadout, skill_spec

    def test_execute_skill_success(self, setup):
        service, pmap, status, loadout, skill_spec = setup
        
        params = service.execute_skill(
            physical_map=pmap,
            player_status=status,
            skill_loadout=loadout,
            skill_spec=skill_spec,
            slot_index=0,
            current_tick=0
        )
        
        assert len(params) == 1
        assert status.mp.value == 90
        assert loadout.can_use_skill(0, 5) is False # Cooldown
        assert pmap.get_actor(WorldObjectId(100)).direction == DirectionEnum.SOUTH

    def test_execute_skill_with_auto_aim(self, setup):
        service, pmap, status, loadout, skill_spec = setup
        
        # 敵を東(7, 5)に配置
        enemy = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(200))
        )
        pmap.add_object(enemy)
        
        params = service.execute_skill(
            physical_map=pmap,
            player_status=status,
            skill_loadout=loadout,
            skill_spec=skill_spec,
            slot_index=0,
            current_tick=0,
            auto_aim=True
        )
        
        assert pmap.get_actor(WorldObjectId(100)).direction == DirectionEnum.EAST
        assert params[0].initial_coordinate == Coordinate(5, 5)

    def test_execute_skill_insufficient_mp(self, setup):
        service, pmap, status, loadout, skill_spec = setup
        status.consume_resources(mp_cost=95) # Remaining MP 5
        
        from ai_rpg_world.domain.player.exception.player_exceptions import InsufficientMpException
        with pytest.raises(InsufficientMpException):
            service.execute_skill(
                physical_map=pmap,
                player_status=status,
                skill_loadout=loadout,
                skill_spec=skill_spec,
                slot_index=0,
                current_tick=0
            )

    def test_execute_skill_on_cooldown(self, setup):
        service, pmap, status, loadout, skill_spec = setup
        
        # 1回目
        service.execute_skill(pmap, status, loadout, skill_spec, 0, 0)
        
        # 2回目 (Tick 5, Cooldown 10)
        from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillCooldownActiveException
        with pytest.raises(SkillCooldownActiveException):
            service.execute_skill(pmap, status, loadout, skill_spec, 0, 5)
