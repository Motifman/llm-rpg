import pytest
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class TestQuestReward:
    """QuestReward値オブジェクトのテスト"""

    def test_of_empty_reward(self):
        """空の報酬が作成できること"""
        r = QuestReward.of()
        assert r.gold == 0
        assert r.exp == 0
        assert r.item_rewards == ()

    def test_of_gold_exp_only(self):
        """ゴールドと経験値のみの報酬"""
        r = QuestReward.of(gold=100, exp=50)
        assert r.gold == 100
        assert r.exp == 50
        assert r.item_rewards == ()

    def test_of_with_items(self):
        """アイテム付き報酬"""
        r = QuestReward.of(
            gold=10,
            exp=5,
            item_rewards=[(ItemSpecId(1), 2), (ItemSpecId(2), 1)],
        )
        assert r.gold == 10
        assert r.exp == 5
        assert len(r.item_rewards) == 2
        assert r.item_rewards[0] == (ItemSpecId(1), 2)
        assert r.item_rewards[1] == (ItemSpecId(2), 1)

    def test_negative_gold_raises(self):
        """負のゴールドは例外"""
        with pytest.raises(ValueError):
            QuestReward.of(gold=-1)

    def test_negative_exp_raises(self):
        """負の経験値は例外"""
        with pytest.raises(ValueError):
            QuestReward.of(exp=-1)

    def test_item_quantity_zero_raises(self):
        """アイテム数量が0は例外"""
        with pytest.raises(ValueError):
            QuestReward.of(item_rewards=[(ItemSpecId(1), 0)])
