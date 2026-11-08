from __future__ import annotations

from enum import Enum

import pytest

from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import FlawCollector, Unreadable, YamlNode


class _Lighting(Enum):
    BRIGHT = "BRIGHT"
    VERY_DARK = "VERY_DARK"


def _node(value: object) -> YamlNode:
    return YamlNode(value, YamlPath.root() / "spots" / "mine")


def _location_of(raised: pytest.ExceptionInfo[Unreadable]) -> DesignLocation:
    return raised.value.flaw.location


class TestYamlNode:
    """YamlNode が欄の欠け・型の違い・知らない欄を、その場所を付けた Unreadable にすることを保証する。"""

    def test_missing_required_field_is_unreadable_at_that_field(self) -> None:
        """必須の欄が無いと、素の KeyError ではなく、その欄の場所を付けた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _node({}).fields("name").required("name")

        assert _location_of(raised) == DesignLocation("spot", "mine", "name")

    def test_unknown_field_is_unreadable_at_that_field(self) -> None:
        """宣言に無い欄を書くと、綴り違いを見逃さないよう、その欄の場所を付けた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _node({"name": "坑道", "nmae": "x"}).fields("name")

        assert _location_of(raised) == DesignLocation("spot", "mine", "nmae")

    def test_text_of_wrong_type_is_unreadable(self) -> None:
        """文の欄に数を書くと Unreadable になる。"""
        with pytest.raises(Unreadable):
            _node(3).text()

    def test_boolean_is_not_read_as_integer(self) -> None:
        """数の欄に true を書いても、1 として読まずに Unreadable にする。"""
        with pytest.raises(Unreadable):
            _node(True).integer()

    def test_enum_is_read_from_lower_snake_case(self) -> None:
        """列挙は、名前を小文字の snake_case で書く。"""
        assert _node("very_dark").enum(_Lighting) is _Lighting.VERY_DARK

    def test_misspelled_enum_is_unreadable_with_choices(self) -> None:
        """列挙の綴り違いは、選べる値を理由に並べた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _node("dimm").enum(_Lighting)

        assert "bright" in raised.value.flaw.reason

    def test_domain_exception_while_building_is_unreadable_at_the_node(self) -> None:
        """宣言の型が作るときに投げたドメイン例外は、その節の場所を付けた Unreadable に包む。"""

        def broken() -> object:
            raise ValueOutOfRangeException("capacity must be at least 1")

        with pytest.raises(Unreadable) as raised:
            _node({}).build(broken)

        assert _location_of(raised) == DesignLocation("spot", "mine", "")
        assert "capacity must be at least 1" in raised.value.flaw.reason


class TestFlawCollector:
    """FlawCollector が読めなかった宣言を飛ばし、誤りを集め続けることを保証する。"""

    def test_collects_every_unreadable_and_keeps_readable_results(self) -> None:
        """読めない宣言が 2 つあっても止まらず、2 つの誤りを集め、読めた宣言だけを返す。"""
        collector = FlawCollector(ScenarioOrigins())
        results = [
            collector.attempt(lambda: _node({}).fields("name").required("name")),
            collector.attempt(lambda: "読めた"),
            collector.attempt(lambda: _node(1).text()),
        ]

        assert [result for result in results if result is not None] == ["読めた"]
        assert len(collector.flaws) == 2
