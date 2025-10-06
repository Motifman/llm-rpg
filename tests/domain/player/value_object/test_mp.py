import pytest
from src.domain.player.value_object.mp import Mp
from src.domain.player.exception import MpValidationException


class TestMp:
    """Mp値オブジェクトのテスト"""

    def test_create_mp_success(self):
        """正常作成のテスト"""
        mp = Mp.create(30, 100)
        assert mp.value == 30
        assert mp.max_mp == 100

    def test_create_mp_with_value_over_max(self):
        """最大値を超える値を指定した場合、値が制限される"""
        mp = Mp.create(150, 100)
        assert mp.value == 100
        assert mp.max_mp == 100

    def test_create_mp_with_negative_value(self):
        """負の値を指定した場合、値が制限される"""
        mp = Mp.create(-10, 100)
        assert mp.value == 0
        assert mp.max_mp == 100

    def test_direct_instantiation_negative_max_mp(self):
        """直接インスタンス化でmax_mpが負の値の場合"""
        with pytest.raises(MpValidationException, match="max_mpは0以上の値である必要があります"):
            Mp(30, -10)

    def test_direct_instantiation_negative_value(self):
        """直接インスタンス化でvalueが負の値の場合"""
        with pytest.raises(MpValidationException, match="MPは0以上の値である必要があります"):
            Mp(-10, 100)

    def test_direct_instantiation_value_over_max(self):
        """直接インスタンス化でvalueがmax_mpを超える場合"""
        with pytest.raises(MpValidationException, match="MPはmax_mp以下の値である必要があります"):
            Mp(150, 100)

    def test_heal_success(self):
        """回復のテスト（正常系）"""
        mp = Mp.create(30, 100)
        healed_mp = mp.heal(20)
        assert healed_mp.value == 50
        assert healed_mp.max_mp == 100

    def test_heal_over_max(self):
        """回復で最大値を超える場合"""
        mp = Mp.create(90, 100)
        healed_mp = mp.heal(20)
        assert healed_mp.value == 100
        assert healed_mp.max_mp == 100

    def test_heal_negative_amount(self):
        """回復量が負の値の場合"""
        mp = Mp.create(30, 100)
        with pytest.raises(MpValidationException, match="回復量は0以上の値である必要があります"):
            mp.heal(-10)

    def test_consume_success(self):
        """消費のテスト（正常系）"""
        mp = Mp.create(50, 100)
        consumed_mp = mp.consume(20)
        assert consumed_mp.value == 30
        assert consumed_mp.max_mp == 100

    def test_consume_over_current(self):
        """消費量が現在のMPを超える場合"""
        mp = Mp.create(10, 100)
        consumed_mp = mp.consume(50)
        assert consumed_mp.value == 0
        assert consumed_mp.max_mp == 100

    def test_consume_negative_amount(self):
        """消費量が負の値の場合"""
        mp = Mp.create(50, 100)
        with pytest.raises(MpValidationException, match="消費量は0以上の値である必要があります"):
            mp.consume(-10)

    def test_can_consume_success(self):
        """消費可能チェック（正常系）"""
        mp = Mp.create(50, 100)
        assert mp.can_consume(30) == True
        assert mp.can_consume(50) == True
        assert mp.can_consume(60) == False

    def test_can_consume_negative_amount(self):
        """消費量が負の値の場合"""
        mp = Mp.create(50, 100)
        with pytest.raises(MpValidationException, match="消費量は0以上の値である必要があります"):
            mp.can_consume(-10)

    def test_is_empty(self):
        """空状態チェック"""
        assert Mp.create(0, 100).is_empty() == True
        assert Mp.create(1, 100).is_empty() == False
        assert Mp.create(0, 0).is_empty() == True

    def test_is_full(self):
        """満タン状態チェック"""
        assert Mp.create(100, 100).is_full() == True
        assert Mp.create(50, 100).is_full() == False
        assert Mp.create(0, 0).is_full() == True  # max_mpが0の場合は常にTrue

    def test_get_percentage(self):
        """割合取得"""
        assert Mp.create(50, 100).get_percentage() == 0.5
        assert Mp.create(0, 100).get_percentage() == 0.0
        assert Mp.create(100, 100).get_percentage() == 1.0
        assert Mp.create(10, 0).get_percentage() == 0.0  # max_mpが0の場合は0.0

    def test_string_representation(self):
        """文字列表示"""
        mp = Mp.create(30, 100)
        assert str(mp) == "30/100"

    def test_equality(self):
        """等価性比較"""
        mp1 = Mp.create(30, 100)
        mp2 = Mp.create(30, 100)
        mp3 = Mp.create(20, 100)
        mp4 = Mp.create(30, 80)

        assert mp1 == mp2
        assert mp1 != mp3
        assert mp1 != mp4
        assert mp1 != "not mp"

    def test_hash(self):
        """ハッシュ値"""
        mp1 = Mp.create(30, 100)
        mp2 = Mp.create(30, 100)
        mp3 = Mp.create(20, 100)

        assert hash(mp1) == hash(mp2)
        assert hash(mp1) != hash(mp3)

        # setで使用可能
        mp_set = {mp1, mp2, mp3}
        assert len(mp_set) == 2

    def test_immutability(self):
        """不変性のテスト"""
        mp1 = Mp.create(30, 100)
        mp2 = mp1.heal(10)

        # 元のインスタンスは変更されていない
        assert mp1.value == 30
        assert mp2.value == 40
