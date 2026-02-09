import pytest
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException


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
