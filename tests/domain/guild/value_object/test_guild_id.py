import pytest
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.exception.guild_exception import GuildIdValidationException


class TestGuildId:
    """GuildId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        guild_id = GuildId(1)
        assert guild_id.value == 1

    def test_create_large_positive_int_id(self):
        """大きな正の整数値で作成できること"""
        guild_id = GuildId(999999)
        assert guild_id.value == 999999

    def test_create_from_int_create_method(self):
        """createメソッドでintから作成できること"""
        guild_id = GuildId.create(123)
        assert guild_id.value == 123
        assert isinstance(guild_id, GuildId)

    def test_create_from_str_create_method(self):
        """createメソッドでstrから作成できること"""
        guild_id = GuildId.create("456")
        assert guild_id.value == 456
        assert isinstance(guild_id, GuildId)

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(GuildIdValidationException):
            GuildId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(GuildIdValidationException):
            GuildId(-1)
        with pytest.raises(GuildIdValidationException):
            GuildId(-100)

    def test_create_from_negative_str_raises_error(self):
        """負の文字列から作成できないこと"""
        with pytest.raises(GuildIdValidationException):
            GuildId.create("-5")

    def test_create_from_zero_str_raises_error(self):
        """0の文字列から作成できないこと"""
        with pytest.raises(GuildIdValidationException):
            GuildId.create("0")

    def test_create_from_invalid_str_raises_error(self):
        """無効な文字列から作成できないこと"""
        with pytest.raises(GuildIdValidationException):
            GuildId.create("abc")
        with pytest.raises(GuildIdValidationException):
            GuildId.create("12.5")
        with pytest.raises(GuildIdValidationException):
            GuildId.create("")

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        guild_id = GuildId(789)
        assert str(guild_id) == "789"

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        guild_id = GuildId(101)
        assert int(guild_id) == 101

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        g1, g2, g3 = GuildId(202), GuildId(202), GuildId(303)
        assert g1 == g2
        assert g1 != g3
        assert g1 != "not a guild id"
        assert g1 != 202

    def test_hash(self):
        """ハッシュが正しく動作すること"""
        g1, g2 = GuildId(1), GuildId(1)
        assert hash(g1) == hash(g2)
