from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.person_conditions import HasItemCondition, IsInSectionCondition
from ai_rpg_world.game_world.domain.condition.subject import Actor, EachPerson, NamedPerson
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count, DescriptionText, FlagId
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import read_yaml_document
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import Unreadable, YamlNode
from tests.game_world.support.world_design_for_tests import character, item_spec, nouns, section, spot

GENERATOR = FlagDeclaration(FlagId("generator_running"), DescriptionText("発電機が動いている"), initially_raised=False)
DEPARTED = FlagDeclaration(FlagId("lift_departed"), DescriptionText("籠が上がった"), initially_raised=False)
NOUNS = nouns(
    flags=(GENERATOR, DEPARTED),
    spots=(spot("lift_landing"),),
    item_specs=(item_spec("lift_key"),),
    sections=(section("cage", "lift_landing"),),
    characters=(character("haru", "lift_landing"),),
)
AT = YamlPath.root() / "spots" / "lift_landing" / "objects" / "lift_panel" / "interactions" / "start_lift"


def _read(text: str) -> object:
    reader = ConditionReader(DeclaredNames(NOUNS, frozenset()))
    return reader.read(YamlNode(read_yaml_document(text).value, AT / "precondition"))


class TestConditionNode:
    """ConditionReader が、種類を鍵にした地図の節を条件の型に読むことを保証する。"""

    def test_reads_precondition_written_in_the_format_document(self) -> None:
        """scenario_format.md の操作盤の前提の形を、条件の木と各節の断りの文に読む。"""
        condition = _read(
            "all_of:\n"
            "  - not: { flag_is_raised: lift_departed }\n"
            "    failure_text: 籠はもう上がってしまった。\n"
            "  - has_item: { who: actor, item_spec: lift_key, count: 1 }\n"
            "  - flag_is_raised: generator_running\n"
            "failure_text: 昇降機は動かない。\n"
        )

        assert condition == AllOfCondition(
            children=(
                NotCondition(
                    child=FlagIsRaisedCondition(DEPARTED, NoText()),
                    failure_text=TextWithUnassignedPeople("籠はもう上がってしまった。"),
                ),
                HasItemCondition(Actor(), NOUNS.item_spec("lift_key", AT.location()), Count(1), NoText()),
                FlagIsRaisedCondition(GENERATOR, NoText()),
            ),
            failure_text=TextWithUnassignedPeople("昇降機は動かない。"),
        )

    def test_single_field_may_be_written_directly_or_by_name(self) -> None:
        """欄が 1 つだけの種類は、値に直接書いても、欄の名前を書いても同じ条件になる。"""
        assert _read("flag_is_raised: lift_departed") == _read("flag_is_raised: { flag: lift_departed }")

    def test_named_person_is_read_as_subject(self) -> None:
        """主語は actor などの語のほか、{ named: <登場人物> } で名指しの人を書ける。"""
        condition = _read("is_in_section: { who: { named: haru }, section: cage }")

        assert isinstance(condition, IsInSectionCondition)
        assert isinstance(condition.who, NamedPerson)

    def test_each_person_is_read_as_subject(self) -> None:
        """each_person は EachPerson の主語になる。"""
        condition = _read("is_in_section: { who: each_person, section: cage }")

        assert isinstance(condition, IsInSectionCondition) and condition.who == EachPerson()

    @pytest.mark.parametrize(
        "text",
        [
            "flag_is_raised: lift_departed\nhas_item: { who: actor, item_spec: lift_key, count: 1 }\n",
            "failure_text: 動かない。\n",
        ],
    )
    def test_node_without_exactly_one_kind_is_unreadable_at_the_node(self, text: str) -> None:
        """種類の鍵が 2 つある節も 0 個の節も、その節の場所を付けた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _read(text)

        assert raised.value.flaw.location == DesignLocation(
            "object", "lift_panel", "interactions.start_lift.precondition"
        )

    def test_unknown_kind_is_unreadable_at_the_kind(self) -> None:
        """知らない種類の鍵は、その鍵の場所を付けた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _read("flag_raised: lift_departed")

        assert raised.value.flaw.location.field == "interactions.start_lift.precondition.flag_raised"

    def test_missing_field_inside_kind_is_unreadable_not_key_error(self) -> None:
        """種類の中の必須の欄が欠けていても、素の KeyError ではなく Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _read("has_item: { who: actor, item_spec: lift_key }")

        assert raised.value.flaw.location.field == "interactions.start_lift.precondition.has_item.count"
