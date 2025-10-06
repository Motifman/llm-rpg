import pytest
from src.domain.player.value_object.base_status import BaseStatus, EMPTY_STATUS
from src.domain.player.exception import BaseStatusValidationException


class TestBaseStatus:
    """BaseStatus値オブジェクトのテスト"""

    def test_create_success(self):
        """正常作成のテスト"""
        status = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        assert status.attack == 10
        assert status.defense == 20
        assert status.speed == 30
        assert status.critical_rate == 0.5
        assert status.evasion_rate == 0.3

    def test_direct_instantiation_negative_attack(self):
        """attackが負の値の場合"""
        with pytest.raises(BaseStatusValidationException, match="attackは0以上の値である必要があります"):
            BaseStatus(-1, 20, 30, 0.5, 0.3)

    def test_direct_instantiation_negative_defense(self):
        """defenseが負の値の場合"""
        with pytest.raises(BaseStatusValidationException, match="defenseは0以上の値である必要があります"):
            BaseStatus(10, -1, 30, 0.5, 0.3)

    def test_direct_instantiation_negative_speed(self):
        """speedが負の値の場合"""
        with pytest.raises(BaseStatusValidationException, match="speedは0以上の値である必要があります"):
            BaseStatus(10, 20, -1, 0.5, 0.3)

    def test_direct_instantiation_critical_rate_too_low(self):
        """critical_rateが0未満の場合"""
        with pytest.raises(BaseStatusValidationException, match="critical_rateは0.0〜1.0の範囲である必要があります"):
            BaseStatus(10, 20, 30, -0.1, 0.3)

    def test_direct_instantiation_critical_rate_too_high(self):
        """critical_rateが1を超える場合"""
        with pytest.raises(BaseStatusValidationException, match="critical_rateは0.0〜1.0の範囲である必要があります"):
            BaseStatus(10, 20, 30, 1.1, 0.3)

    def test_direct_instantiation_evasion_rate_too_low(self):
        """evasion_rateが0未満の場合"""
        with pytest.raises(BaseStatusValidationException, match="evasion_rateは0.0〜1.0の範囲である必要があります"):
            BaseStatus(10, 20, 30, 0.5, -0.1)

    def test_direct_instantiation_evasion_rate_too_high(self):
        """evasion_rateが1を超える場合"""
        with pytest.raises(BaseStatusValidationException, match="evasion_rateは0.0〜1.0の範囲である必要があります"):
            BaseStatus(10, 20, 30, 0.5, 1.1)

    def test_add_success(self):
        """加算のテスト（正常系）"""
        status1 = BaseStatus.create(10, 20, 30, 0.2, 0.3)
        status2 = BaseStatus.create(5, 10, 15, 0.1, 0.2)
        result = status1 + status2

        assert result.attack == 15
        assert result.defense == 30
        assert result.speed == 45
        assert abs(result.critical_rate - 0.3) < 1e-10
        assert abs(result.evasion_rate - 0.5) < 1e-10

    def test_add_with_rate_overflow(self):
        """加算でレートが1.0を超える場合、1.0に制限される"""
        status1 = BaseStatus.create(10, 20, 30, 0.8, 0.9)
        status2 = BaseStatus.create(5, 10, 15, 0.5, 0.5)
        result = status1 + status2

        assert result.critical_rate == 1.0
        assert result.evasion_rate == 1.0

    def test_add_invalid_type(self):
        """無効な型との加算"""
        status = BaseStatus.create(10, 20, 30, 0.2, 0.3)
        with pytest.raises(TypeError, match="BaseStatus同士の加算のみ可能です"):
            status + "invalid"

    def test_sub_success(self):
        """減算のテスト（正常系）"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.7)
        status2 = BaseStatus.create(3, 5, 8, 0.2, 0.3)
        result = status1 - status2

        assert result.attack == 7
        assert result.defense == 15
        assert result.speed == 22
        assert abs(result.critical_rate - 0.3) < 1e-10
        assert abs(result.evasion_rate - 0.4) < 1e-10

    def test_sub_with_negative_result(self):
        """減算で負の値になる場合、0に制限される"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.7)
        status2 = BaseStatus.create(15, 25, 35, 0.8, 0.9)
        result = status1 - status2

        assert result.attack == 0
        assert result.defense == 0
        assert result.speed == 0
        assert result.critical_rate == 0.0
        assert result.evasion_rate == 0.0

    def test_sub_invalid_type(self):
        """無効な型との減算"""
        status = BaseStatus.create(10, 20, 30, 0.2, 0.3)
        with pytest.raises(TypeError, match="BaseStatus同士の減算のみ可能です"):
            status - "invalid"

    def test_get_total_points(self):
        """合計ポイント取得"""
        status = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        assert status.get_total_points() == 60

    def test_string_representation(self):
        """文字列表示"""
        status = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        expected = "ATK:10 DEF:20 SPD:30 CRT:0.50 EVA:0.30"
        assert str(status) == expected

    def test_equality(self):
        """等価性比較"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status2 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status3 = BaseStatus.create(5, 20, 30, 0.5, 0.3)
        status4 = BaseStatus.create(10, 15, 30, 0.5, 0.3)

        assert status1 == status2
        assert status1 != status3
        assert status1 != status4
        assert status1 != "not status"

    def test_equality_with_floating_point_precision(self):
        """浮動小数点の精度を考慮した等価性比較"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status2 = BaseStatus(10, 20, 30, 0.5 + 1e-11, 0.3 - 1e-11)  # 非常に小さな差

        assert status1 == status2  # 許容範囲内の差は等価とみなされる

    def test_hash(self):
        """ハッシュ値"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status2 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status3 = BaseStatus.create(5, 20, 30, 0.5, 0.3)

        assert hash(status1) == hash(status2)
        assert hash(status1) != hash(status3)

        # setで使用可能
        status_set = {status1, status2, status3}
        assert len(status_set) == 2

    def test_immutability(self):
        """不変性のテスト"""
        status1 = BaseStatus.create(10, 20, 30, 0.5, 0.3)
        status2 = status1 + BaseStatus.create(5, 5, 5, 0.1, 0.1)

        # 元のインスタンスは変更されていない
        assert status1.attack == 10
        assert status1.defense == 20
        assert status2.attack == 15
        assert status2.defense == 25

    def test_empty_status(self):
        """EMPTY_STATUSのテスト"""
        assert EMPTY_STATUS.attack == 0
        assert EMPTY_STATUS.defense == 0
        assert EMPTY_STATUS.speed == 0
        assert EMPTY_STATUS.critical_rate == 0.0
        assert EMPTY_STATUS.evasion_rate == 0.0

    def test_empty_status_string(self):
        """EMPTY_STATUSの文字列表示"""
        expected = "ATK:0 DEF:0 SPD:0 CRT:0.00 EVA:0.00"
        assert str(EMPTY_STATUS) == expected
