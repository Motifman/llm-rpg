import pytest
from src.domain.player.value_object.player_name import PlayerName
from src.domain.player.exception.player_exceptions import PlayerNameValidationException


class TestPlayerName:
    """PlayerName値オブジェクトのテスト"""

    def test_create_min_length_name(self):
        """最小文字数（3文字）で作成できること"""
        name = PlayerName("ABC")
        assert name.value == "ABC"

    def test_create_max_length_name(self):
        """最大文字数（16文字）で作成できること"""
        name = PlayerName("ABCDEFGHIJKLMNOP")
        assert name.value == "ABCDEFGHIJKLMNOP"

    def test_create_normal_length_name(self):
        """通常の文字数で作成できること"""
        name = PlayerName("TestPlayer")
        assert name.value == "TestPlayer"

    def test_create_with_unicode_characters(self):
        """Unicode文字を含む名前で作成できること"""
        name = PlayerName("テストプレイヤー")
        assert name.value == "テストプレイヤー"

    def test_create_with_spaces(self):
        """スペースを含む名前で作成できること"""
        name = PlayerName("Test Player")
        assert name.value == "Test Player"

    def test_create_empty_name_raises_error(self):
        """空文字の名前は作成できないこと"""
        with pytest.raises(PlayerNameValidationException, match="Name cannot be empty"):
            PlayerName("")

    def test_create_too_short_name_raises_error(self):
        """2文字以下の名前は作成できないこと"""
        with pytest.raises(PlayerNameValidationException, match="Name must be between 3 and 16 characters"):
            PlayerName("AB")

        with pytest.raises(PlayerNameValidationException, match="Name must be between 3 and 16 characters"):
            PlayerName("A")

    def test_create_too_long_name_raises_error(self):
        """17文字以上の名前は作成できないこと"""
        long_name = "A" * 17
        with pytest.raises(PlayerNameValidationException, match="Name must be between 3 and 16 characters"):
            PlayerName(long_name)

        longer_name = "A" * 100
        with pytest.raises(PlayerNameValidationException, match="Name must be between 3 and 16 characters"):
            PlayerName(longer_name)

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        name1 = PlayerName("TestPlayer")
        name2 = PlayerName("TestPlayer")
        name3 = PlayerName("DifferentPlayer")

        assert name1 == name2
        assert name1 != name3
        assert name1 != "not a name"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        name1 = PlayerName("TestPlayer")
        name2 = PlayerName("TestPlayer")

        assert hash(name1) == hash(name2)

        # setで重複が除去されることを確認
        name_set = {name1, name2}
        assert len(name_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        name = PlayerName("TestPlayer")
        original_value = name.value

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            name.value = "ModifiedName"

        # 元の値は変わっていないことを確認
        assert name.value == original_value
