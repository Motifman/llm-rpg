import pytest
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.exception.quest_exception import QuestIdValidationException


class TestQuestId:
    """QuestId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        quest_id = QuestId(1)
        assert quest_id.value == 1

    def test_create_large_positive_int_id(self):
        """大きな正の整数値で作成できること"""
        quest_id = QuestId(999999)
        assert quest_id.value == 999999

    def test_create_from_int_create_method(self):
        """createメソッドでintから作成できること"""
        quest_id = QuestId.create(123)
        assert quest_id.value == 123
        assert isinstance(quest_id, QuestId)

    def test_create_from_str_create_method(self):
        """createメソッドでstrから作成できること"""
        quest_id = QuestId.create("456")
        assert quest_id.value == 456
        assert isinstance(quest_id, QuestId)

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(QuestIdValidationException):
            QuestId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(QuestIdValidationException):
            QuestId(-1)
        with pytest.raises(QuestIdValidationException):
            QuestId(-100)

    def test_create_from_negative_str_raises_error(self):
        """負の文字列から作成できないこと"""
        with pytest.raises(QuestIdValidationException):
            QuestId.create("-5")

    def test_create_from_zero_str_raises_error(self):
        """0の文字列から作成できないこと"""
        with pytest.raises(QuestIdValidationException):
            QuestId.create("0")

    def test_create_from_invalid_str_raises_error(self):
        """無効な文字列から作成できないこと"""
        with pytest.raises(QuestIdValidationException):
            QuestId.create("abc")
        with pytest.raises(QuestIdValidationException):
            QuestId.create("12.5")
        with pytest.raises(QuestIdValidationException):
            QuestId.create("")

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        quest_id = QuestId(789)
        assert str(quest_id) == "789"

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        quest_id = QuestId(101)
        assert int(quest_id) == 101

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        q1, q2, q3 = QuestId(202), QuestId(202), QuestId(303)
        assert q1 == q2
        assert q1 != q3
        assert q1 != "not a quest id"
        assert q1 != 202

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        q1, q2 = QuestId(404), QuestId(404)
        assert hash(q1) == hash(q2)
        assert len({q1, q2}) == 1
