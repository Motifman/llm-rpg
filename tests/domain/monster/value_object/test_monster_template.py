import pytest
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage, MAX_GROWTH_STAGES
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

    def test_create_fail_whitespace_only_name(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """名前が空白のみの場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="Monster name cannot be empty"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="   ",
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

    def test_create_success_with_growth_stages(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """growth_stages を指定して作成できること"""
        stages = [
            GrowthStage(after_ticks=0, stats_multiplier=0.8),
            GrowthStage(after_ticks=100, stats_multiplier=1.0),
        ]
        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Dragon",
            base_stats=valid_base_stats,
            reward_info=valid_reward_info,
            respawn_info=valid_respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="Grows over time.",
            growth_stages=stages,
        )
        assert len(template.growth_stages) == 2
        assert template.growth_stages[0].after_ticks == 0
        assert template.growth_stages[0].stats_multiplier == 0.8
        assert template.growth_stages[1].after_ticks == 100
        assert template.growth_stages[1].stats_multiplier == 1.0

    def test_create_success_with_empty_growth_stages_defaults_to_empty_list(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """growth_stages を渡さない場合は空リストになること"""
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
        assert template.growth_stages == []

    def test_create_fail_growth_stages_not_list(self, valid_base_stats, valid_reward_info, valid_respawn_info):
        """growth_stages がリストでない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="growth_stages must be a list"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                growth_stages=GrowthStage(after_ticks=0, stats_multiplier=1.0),
            )

    def test_create_fail_growth_stages_element_not_growth_stage(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """growth_stages の要素が GrowthStage でない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="must be GrowthStage"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                growth_stages=[(0, 0.8), (100, 1.0)],
            )

    def test_create_fail_growth_stages_not_ordered_by_after_ticks(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """growth_stages が after_ticks の昇順でない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="ordered by after_ticks ascending"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                growth_stages=[
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                    GrowthStage(after_ticks=0, stats_multiplier=0.8),
                ],
            )

    def test_create_fail_first_growth_stage_not_zero(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """最初の growth_stage の after_ticks が 0 でない場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match="after_ticks=0"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                growth_stages=[
                    GrowthStage(after_ticks=10, stats_multiplier=0.8),
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                ],
            )

    def test_create_fail_growth_stages_exceeds_max(
        self, valid_base_stats, valid_reward_info, valid_respawn_info
    ):
        """growth_stages が MAX_GROWTH_STAGES を超える場合はエラーが発生すること"""
        with pytest.raises(MonsterTemplateValidationException, match=f"at most {MAX_GROWTH_STAGES}"):
            MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A weak blue slime.",
                growth_stages=[
                    GrowthStage(after_ticks=0, stats_multiplier=0.5),
                    GrowthStage(after_ticks=50, stats_multiplier=0.8),
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                    GrowthStage(after_ticks=200, stats_multiplier=1.0),
                    GrowthStage(after_ticks=300, stats_multiplier=1.0),
                ],
            )

    class TestHungerParams:
        """Phase 6: 飢餓パラメータのバリデーション"""

        def test_create_with_hunger_params_success(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """有効な飢餓パラメータで作成できること"""
            template = MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Wolf",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A wolf.",
                hunger_increase_per_tick=0.001,
                hunger_decrease_on_prey_kill=0.3,
                hunger_starvation_threshold=0.8,
                starvation_ticks=50,
            )
            assert template.hunger_increase_per_tick == 0.001
            assert template.hunger_decrease_on_prey_kill == 0.3
            assert template.hunger_starvation_threshold == 0.8
            assert template.starvation_ticks == 50

        def test_create_with_default_hunger_params(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """飢餓パラメータ省略時はデフォルトで無効になること"""
            template = MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Slime",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A slime.",
            )
            assert template.hunger_increase_per_tick == 0.0
            assert template.hunger_decrease_on_prey_kill == 0.0
            assert template.hunger_starvation_threshold == 1.0
            assert template.starvation_ticks == 0

        def test_create_fail_hunger_increase_negative(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """hunger_increase_per_tick が負の場合はエラー"""
            with pytest.raises(MonsterTemplateValidationException, match="hunger_increase_per_tick"):
                MonsterTemplate(
                    template_id=MonsterTemplateId.create(1),
                    name="X",
                    base_stats=valid_base_stats,
                    reward_info=valid_reward_info,
                    respawn_info=valid_respawn_info,
                    race=Race.BEAST,
                    faction=MonsterFactionEnum.ENEMY,
                    description="X",
                    hunger_increase_per_tick=-0.01,
                )

        def test_create_fail_hunger_decrease_negative(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """hunger_decrease_on_prey_kill が負の場合はエラー"""
            with pytest.raises(MonsterTemplateValidationException, match="hunger_decrease_on_prey_kill"):
                MonsterTemplate(
                    template_id=MonsterTemplateId.create(1),
                    name="X",
                    base_stats=valid_base_stats,
                    reward_info=valid_reward_info,
                    respawn_info=valid_respawn_info,
                    race=Race.BEAST,
                    faction=MonsterFactionEnum.ENEMY,
                    description="X",
                    hunger_decrease_on_prey_kill=-0.1,
                )

        def test_create_fail_hunger_starvation_threshold_out_of_range(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """hunger_starvation_threshold が 0.0〜1.0 の範囲外の場合はエラー"""
            with pytest.raises(MonsterTemplateValidationException, match="hunger_starvation_threshold"):
                MonsterTemplate(
                    template_id=MonsterTemplateId.create(1),
                    name="X",
                    base_stats=valid_base_stats,
                    reward_info=valid_reward_info,
                    respawn_info=valid_respawn_info,
                    race=Race.BEAST,
                    faction=MonsterFactionEnum.ENEMY,
                    description="X",
                    hunger_starvation_threshold=1.5,
                )

        def test_create_fail_starvation_ticks_negative(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """starvation_ticks が負の場合はエラー"""
            with pytest.raises(MonsterTemplateValidationException, match="starvation_ticks"):
                MonsterTemplate(
                    template_id=MonsterTemplateId.create(1),
                    name="X",
                    base_stats=valid_base_stats,
                    reward_info=valid_reward_info,
                    respawn_info=valid_respawn_info,
                    race=Race.BEAST,
                    faction=MonsterFactionEnum.ENEMY,
                    description="X",
                    starvation_ticks=-1,
                )

    class TestMaxAgeTicks:
        """max_age_ticks のバリデーション"""

        def test_create_success_none(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """max_age_ticks が None の場合は有効"""
            t = MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="X",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="X",
            )
            assert t.max_age_ticks is None

        def test_create_success_zero(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """max_age_ticks が 0 の場合は有効（無効扱い）"""
            t = MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="X",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="X",
                max_age_ticks=0,
            )
            assert t.max_age_ticks == 0

        def test_create_success_positive(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """max_age_ticks が正の場合は有効"""
            t = MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="X",
                base_stats=valid_base_stats,
                reward_info=valid_reward_info,
                respawn_info=valid_respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="X",
                max_age_ticks=1000,
            )
            assert t.max_age_ticks == 1000

        def test_create_fail_max_age_ticks_negative(
            self, valid_base_stats, valid_reward_info, valid_respawn_info
        ):
            """max_age_ticks が負の場合はエラー"""
            with pytest.raises(MonsterTemplateValidationException, match="max_age_ticks"):
                MonsterTemplate(
                    template_id=MonsterTemplateId.create(1),
                    name="X",
                    base_stats=valid_base_stats,
                    reward_info=valid_reward_info,
                    respawn_info=valid_respawn_info,
                    race=Race.BEAST,
                    faction=MonsterFactionEnum.ENEMY,
                    description="X",
                    max_age_ticks=-1,
                )
