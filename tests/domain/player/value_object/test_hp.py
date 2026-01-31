import pytest
from datetime import datetime
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.exception import HpValidationException


class TestHp:
    """Hp値オブジェクトのテスト"""

    def test_create_hp_success(self):
        """正常作成のテスト"""
        hp = Hp.create(50, 100)
        assert hp.value == 50
        assert hp.max_hp == 100

    def test_create_hp_with_value_over_max(self):
        """最大値を超える値を指定した場合、値が制限される"""
        hp = Hp.create(150, 100)
        assert hp.value == 100
        assert hp.max_hp == 100

    def test_create_hp_with_negative_value(self):
        """負の値を指定した場合、値が制限される"""
        hp = Hp.create(-10, 100)
        assert hp.value == 0
        assert hp.max_hp == 100

    def test_create_hp_with_zero_max_hp(self):
        """max_hpが0の場合"""
        hp = Hp.create(10, 0)
        assert hp.value == 0
        assert hp.max_hp == 0

    def test_direct_instantiation_with_valid_values(self):
        """直接インスタンス化（正常系）"""
        hp = Hp(50, 100)
        assert hp.value == 50
        assert hp.max_hp == 100

    def test_direct_instantiation_negative_max_hp(self):
        """直接インスタンス化でmax_hpが負の値の場合"""
        with pytest.raises(HpValidationException, match="max_hpは0以上の値である必要があります"):
            Hp(50, -10)

    def test_direct_instantiation_negative_value(self):
        """直接インスタンス化でvalueが負の値の場合"""
        with pytest.raises(HpValidationException, match="HPは0以上の値である必要があります"):
            Hp(-10, 100)

    def test_direct_instantiation_value_over_max(self):
        """直接インスタンス化でvalueがmax_hpを超える場合"""
        with pytest.raises(HpValidationException, match="HPはmax_hp以下の値である必要があります"):
            Hp(150, 100)

    def test_heal_success(self):
        """回復のテスト（正常系）"""
        hp = Hp.create(50, 100)
        healed_hp = hp.heal(20)
        assert healed_hp.value == 70
        assert healed_hp.max_hp == 100

    def test_heal_over_max(self):
        """回復で最大値を超える場合"""
        hp = Hp.create(90, 100)
        healed_hp = hp.heal(20)
        assert healed_hp.value == 100
        assert healed_hp.max_hp == 100

    def test_heal_negative_amount(self):
        """回復量が負の値の場合"""
        hp = Hp.create(50, 100)
        with pytest.raises(HpValidationException, match="回復量は0以上の値である必要があります"):
            hp.heal(-10)

    def test_damage_success(self):
        """ダメージのテスト（正常系）"""
        hp = Hp.create(50, 100)
        damaged_hp = hp.damage(20)
        assert damaged_hp.value == 30
        assert damaged_hp.max_hp == 100

    def test_damage_over_current(self):
        """ダメージが現在のHPを超える場合"""
        hp = Hp.create(10, 100)
        damaged_hp = hp.damage(50)
        assert damaged_hp.value == 0
        assert damaged_hp.max_hp == 100

    def test_damage_negative_amount(self):
        """ダメージ量が負の値の場合"""
        hp = Hp.create(50, 100)
        with pytest.raises(HpValidationException, match="ダメージ量は0以上の値である必要があります"):
            hp.damage(-10)

    def test_can_consume_success(self):
        """消費可能チェック（正常系）"""
        hp = Hp.create(50, 100)
        assert hp.can_consume(30) == True
        assert hp.can_consume(50) == True
        assert hp.can_consume(60) == False

    def test_can_consume_negative_amount(self):
        """消費量が負の値の場合"""
        hp = Hp.create(50, 100)
        with pytest.raises(HpValidationException, match="消費量は0以上の値である必要があります"):
            hp.can_consume(-10)

    def test_is_alive(self):
        """生存チェック"""
        assert Hp.create(1, 100).is_alive() == True
        assert Hp.create(0, 100).is_alive() == False
        assert Hp.create(0, 0).is_alive() == False

    def test_is_full(self):
        """満タン状態チェック"""
        assert Hp.create(100, 100).is_full() == True
        assert Hp.create(50, 100).is_full() == False
        assert Hp.create(0, 0).is_full() == True  # max_hpが0の場合は常にTrue

    def test_get_percentage(self):
        """割合取得"""
        assert Hp.create(50, 100).get_percentage() == 0.5
        assert Hp.create(0, 100).get_percentage() == 0.0
        assert Hp.create(100, 100).get_percentage() == 1.0
        assert Hp.create(10, 0).get_percentage() == 0.0  # max_hpが0の場合は0.0

    def test_string_representation(self):
        """文字列表示"""
        hp = Hp.create(50, 100)
        assert str(hp) == "50/100"

    def test_equality(self):
        """等価性比較"""
        hp1 = Hp.create(50, 100)
        hp2 = Hp.create(50, 100)
        hp3 = Hp.create(30, 100)
        hp4 = Hp.create(50, 80)

        assert hp1 == hp2
        assert hp1 != hp3
        assert hp1 != hp4
        assert hp1 != "not hp"

    def test_hash(self):
        """ハッシュ値"""
        hp1 = Hp.create(50, 100)
        hp2 = Hp.create(50, 100)
        hp3 = Hp.create(30, 100)

        assert hash(hp1) == hash(hp2)
        assert hash(hp1) != hash(hp3)

        # setで使用可能
        hp_set = {hp1, hp2, hp3}
        assert len(hp_set) == 2

    def test_immutability(self):
        """不変性のテスト"""
        hp1 = Hp.create(50, 100)
        hp2 = hp1.heal(10)

        # 元のインスタンスは変更されていない
        assert hp1.value == 50
        assert hp2.value == 60
