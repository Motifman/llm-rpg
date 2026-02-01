import pytest
from ai_rpg_world.domain.world.value_object.movement_cost import MovementCost
from ai_rpg_world.domain.world.exception.map_exception import MovementCostValidationException


class TestMovementCost:
    """MovementCost値オブジェクトのテスト"""

    def test_create_success(self):
        """正常に作成できること"""
        cost = MovementCost(1.5)
        assert cost.value == 1.5

    def test_create_zero(self):
        """0のコストで作成できること"""
        cost = MovementCost(0.0)
        assert cost.value == 0.0

    def test_create_inf(self):
        """無限大のコストで作成できること"""
        cost = MovementCost(float('inf'))
        assert cost.value == float('inf')

    def test_create_negative_raises_error(self):
        """負のコストは作成できないこと"""
        with pytest.raises(MovementCostValidationException):
            MovementCost(-0.1)

    def test_addition(self):
        """加算が正しく動作すること"""
        c1 = MovementCost(1.0)
        c2 = MovementCost(2.5)
        result = c1 + c2
        assert isinstance(result, MovementCost)
        assert result.value == 3.5

    def test_factory_methods(self):
        """ファクトリメソッドが正しく動作すること"""
        assert MovementCost.zero().value == 0.0
        assert MovementCost.normal().value == 1.0
        assert MovementCost.high().value == 2.0
        assert MovementCost.impassable().value == float('inf')

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        assert MovementCost(1.0) == MovementCost(1.0)
        assert MovementCost(1.0) != MovementCost(1.1)

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        c1 = MovementCost(1.0)
        c2 = MovementCost(1.0)
        assert hash(c1) == hash(c2)
        assert len({c1, c2}) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        cost = MovementCost(1.0)
        with pytest.raises(AttributeError):
            cost.value = 2.0
