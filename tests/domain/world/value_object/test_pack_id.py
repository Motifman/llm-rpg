"""PackId のテスト（既存 Id 系と同様の仕様・例外検証）"""

import pytest
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.exception.map_exception import PackIdValidationException


class TestPackId:
    def test_create_from_string(self):
        pid = PackId.create("wolf_pack_1")
        assert pid.value == "wolf_pack_1"

    def test_create_from_int(self):
        pid = PackId.create(42)
        assert pid.value == "42"

    def test_create_strips_whitespace(self):
        pid = PackId.create("  alpha  ")
        assert pid.value == "alpha"

    def test_empty_raises(self):
        with pytest.raises(PackIdValidationException):
            PackId.create("")
        with pytest.raises(PackIdValidationException):
            PackId("")

    def test_whitespace_only_raises(self):
        with pytest.raises(PackIdValidationException):
            PackId.create("   ")
        with pytest.raises(PackIdValidationException):
            PackId.create("\t\n")

    def test_none_raises(self):
        with pytest.raises(PackIdValidationException):
            PackId.create(None)

    def test_equality(self):
        assert PackId.create(1) == PackId.create("1")
        assert PackId.create("a") != PackId.create("b")

    def test_hash(self):
        assert hash(PackId.create("x")) == hash(PackId.create("x"))

    def test_str(self):
        assert str(PackId.create("p1")) == "p1"

    def test_immutability(self):
        pid = PackId.create("p1")
        with pytest.raises(AttributeError):
            pid.value = "p2"
        assert pid.value == "p1"

    def test_equality_with_non_pack_id(self):
        pid = PackId.create("p1")
        assert pid != "p1"
        assert pid != None
        assert pid != 1
