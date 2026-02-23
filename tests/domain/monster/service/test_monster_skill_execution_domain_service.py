"""
MonsterSkillExecutionDomainService のテスト

正常ケース・例外ケースを網羅する。
"""
import pytest

from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race, Element
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillNotFoundInSlotException
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException


def _sample_template(template_id: int = 1) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name="test-monster",
        base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
        reward_info=RewardInfo(10, 10, 1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.HUMAN,
        faction=MonsterFactionEnum.ENEMY,
        description="Test",
        skill_ids=[SkillId(1)],
    )


def _sample_skill(skill_id: int = 1, mp_cost: int = 10) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.0,
        hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
        mp_cost=mp_cost,
    )


def _create_map(spot_id_int: int = 1) -> PhysicalMapAggregate:
    tiles = [Tile(Coordinate(x, y, 0), TerrainType.road()) for x in range(10) for y in range(10)]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


class TestMonsterSkillExecutionDomainService:
    @pytest.fixture
    def domain_service(self):
        skill_execution = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        return MonsterSkillExecutionDomainService(skill_execution)

    @pytest.fixture
    def base_setup(self):
        """モンスター・ロードアウト・マップの共通セットアップ"""
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        loadout_id = SkillLoadoutId(500)

        pmap = _create_map(1)
        comp = AutonomousBehaviorComponent(direction=DirectionEnum.SOUTH)
        obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=comp)
        pmap.add_object(obj)

        skill = _sample_skill(1, mp_cost=10)
        loadout = SkillLoadoutAggregate.create(loadout_id, 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)

        monster = MonsterAggregate.create(monster_id, _sample_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), spot_id, WorldTick(0))

        return monster, loadout, pmap, world_object_id, spot_id

    def test_execute_success_returns_spawn_params_and_updates_aggregates(self, domain_service, base_setup):
        """正常時: ヒットボックス生成パラメータを返し、MP・クールダウンが更新される"""
        monster, loadout, pmap, _, _ = base_setup
        current_tick = WorldTick(10)

        params = domain_service.execute(
            monster=monster,
            loadout=loadout,
            physical_map=pmap,
            slot_index=0,
            current_tick=current_tick,
        )

        assert len(params) == 1
        assert monster.mp.value == 90
        assert loadout.can_use_skill(0, 10) is False
        assert params[0].initial_coordinate == Coordinate(5, 5, 0)

    def test_execute_skill_not_in_slot_raises_skill_not_found_in_slot(self, domain_service, base_setup):
        """指定スロットにスキルがない場合 SkillNotFoundInSlotException"""
        monster, loadout, pmap, _, _ = base_setup
        # スロット 1 には何も装備していない
        with pytest.raises(SkillNotFoundInSlotException) as excinfo:
            domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=pmap,
                slot_index=1,
                current_tick=WorldTick(10),
            )
        assert "slot" in str(excinfo.value).lower()

    def test_execute_insufficient_mp_raises_domain_exception(self, domain_service, base_setup):
        """MP不足で MonsterInsufficientMpException（DomainException の一種）"""
        monster, loadout, pmap, _, _ = base_setup
        high_cost_skill = _sample_skill(2, mp_cost=200)
        loadout.equip_skill(DeckTier.NORMAL, 1, high_cost_skill)

        with pytest.raises(DomainException) as excinfo:
            domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=pmap,
                slot_index=1,
                current_tick=WorldTick(10),
            )
        assert "MP" in str(excinfo.value) or "mp" in str(excinfo.value).lower()

    def test_execute_monster_not_on_map_raises_object_not_found(self, domain_service, base_setup):
        """モンスターがマップ上にいない場合（get_actor が失敗）ObjectNotFoundException"""
        monster, loadout, pmap, _, _ = base_setup
        # 別のマップ（モンスターオブジェクトがいない）
        other_map = _create_map(99)

        with pytest.raises(ObjectNotFoundException):
            domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=other_map,
                slot_index=0,
                current_tick=WorldTick(10),
            )

    def test_execute_cooldown_active_raises_domain_exception(self, domain_service, base_setup):
        """クールダウン中に使用するとドメイン例外"""
        monster, loadout, pmap, _, _ = base_setup
        current_tick = WorldTick(10)
        domain_service.execute(
            monster=monster,
            loadout=loadout,
            physical_map=pmap,
            slot_index=0,
            current_tick=current_tick,
        )
        # 同一ティックで再使用は不可（cast_lock）
        with pytest.raises(DomainException) as excinfo:
            domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=pmap,
                slot_index=0,
                current_tick=current_tick,
            )
        assert "cast" in str(excinfo.value).lower() or "cooldown" in str(excinfo.value).lower()

    def test_execute_monster_dead_raises_domain_exception(self, domain_service, base_setup):
        """モンスターが死亡状態の場合 use_mp でドメイン例外"""
        monster, loadout, pmap, _, _ = base_setup
        monster.apply_damage(1000, WorldTick(9))

        with pytest.raises(DomainException):
            domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=pmap,
                slot_index=0,
                current_tick=WorldTick(10),
            )
