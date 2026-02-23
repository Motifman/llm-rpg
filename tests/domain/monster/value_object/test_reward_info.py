import pytest
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRewardValidationException
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


class TestRewardInfo:
    """RewardInfo値オブジェクトのテスト"""

    def test_create_success(self):
        reward = RewardInfo(exp=100, gold=50, loot_table_id=1)
        assert reward.exp == 100
        assert reward.gold == 50
        assert reward.loot_table_id == LootTableId(1)

    def test_create_success_minimal(self):
        reward = RewardInfo(exp=0, gold=0)
        assert reward.exp == 0
        assert reward.gold == 0
        assert reward.loot_table_id is None

    def test_create_fail_negative_exp(self):
        with pytest.raises(MonsterRewardValidationException, match="EXP cannot be negative"):
            RewardInfo(exp=-1, gold=50)

    def test_create_fail_negative_gold(self):
        with pytest.raises(MonsterRewardValidationException, match="Gold cannot be negative"):
            RewardInfo(exp=100, gold=-1)
