import pytest
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.world.enum.world_enum import EcologyTypeEnum


@pytest.fixture
def valid_base_stats():
    return BaseStats(
        max_hp=100,
        max_mp=50,
        attack=20,
        defense=15,
        speed=10,
        critical_rate=0.05,
        evasion_rate=0.03
    )


@pytest.fixture
def valid_reward_info():
    return RewardInfo(exp=100, gold=50, loot_table_id="loot_slime_01")


@pytest.fixture
def valid_respawn_info():
    return RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True)


class TestMonsterTemplate:
    """MonsterTemplate値オブジェクトのテスト"""

    def test_create_success(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """有効なパラメータでMonsterTemplateを作成できること"""
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Slime",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A weak blue slime."
        )
        assert template.name == "Slime"
        assert template.description == "A weak blue slime."

    def test_create_fail_empty_name(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """名前が空の場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="Monster name cannot be empty"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime."
            )

    def test_create_fail_empty_description(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """説明文が空の場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="Monster description cannot be empty"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description=""
            )

    def test_create_fail_whitespace_only_description(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """説明文が空白のみの場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="Monster description cannot be empty"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="   "
            )

    def test_create_fail_too_long_description(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """説明文が長すぎる場合はエラーが発生すること"""
        long_description = "a" * 1001
        with pytest.raises(MonsterTemplateValidationException, match="Monster description is too long"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description=long_description
            )

    def test_create_success_with_default_vision_range_and_flee_threshold(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """デフォルトの vision_range / flee_threshold で作成できること"""
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Slime",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A weak blue slime.",
        )
        assert template.vision_range == 5
        assert template.flee_threshold == 0.2

    def test_create_success_with_custom_vision_range_and_flee_threshold(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """vision_range / flee_threshold を指定して作成できること"""
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Eagle",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="Wide vision predator.",
            vision_range=10,
            flee_threshold=0.3,
        )
        assert template.vision_range == 10
        assert template.flee_threshold == 0.3

    def test_create_fail_negative_vision_range(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """vision_range が負の場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="vision_range cannot be negative"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                vision_range=-1,
            )

    def test_create_fail_flee_threshold_out_of_range(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """flee_threshold が 0.0〜1.0 の範囲外の場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="flee_threshold must be between"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                flee_threshold=1.5,
            )

    def test_create_success_with_skill_ids(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """skill_ids に SkillId のリストを指定して作成できること"""
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Mage",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="A mage.",
            skill_ids=[SkillId(1), SkillId(2)],
        )
        assert len(template.skill_ids) == 2
        assert template.skill_ids[0] == SkillId(1)
        assert template.skill_ids[1] == SkillId(2)

    def test_create_fail_skill_ids_not_list(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """skill_ids がリストでない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="skill_ids must be a list"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                skill_ids="not_a_list",
            )

    def test_create_fail_skill_ids_element_not_skill_id(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """skill_ids の要素が SkillId でない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="must be SkillId"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                skill_ids=[1, 2],
            )

    def test_create_fail_ecology_type_not_enum(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """ecology_type が EcologyTypeEnum でない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="ecology_type must be EcologyTypeEnum"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                ecology_type="invalid",
            )

    def test_create_success_with_ecology_type_enum(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """ecology_type に EcologyTypeEnum を渡して作成できること"""
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Slime",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A weak blue slime.",
            ecology_type=EcologyTypeEnum.AMBUSH,
        )
        assert template.ecology_type == EcologyTypeEnum.AMBUSH
