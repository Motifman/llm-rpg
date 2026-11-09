from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    FlagValue,
    Lasts,
    LastsIndefinitely,
    LitWhen,
    NoRefill,
    StockStateKind,
    StockValue,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.value_object import Count, DescriptionText, StateKeyId, Ticks
from ai_rpg_world.game_world.infrastructure.scenario.noun_reader import NounReader, ReadNouns
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import read_yaml_document
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import FlawCollector, YamlNode

_DEFAULTS = """
defaults:
  atmosphere: { outdoor: false, temperature: normal, ambient_sound: null, smell: null }
  object: { state_keys: {} }
  appearance: { seen_in_dark: false, hidden_until_revealed: false }
  item_spec: { state_keys: {}, lights_up: null, hands_needed: 1 }
"""


def _read(text: str) -> tuple[ReadNouns, FlawCollector]:
    root = YamlNode(read_yaml_document(_DEFAULTS + text).value, YamlPath.root())
    fields = root.fields("defaults", "spots", "item_specs", "passages")
    collector = FlawCollector(ScenarioOrigins())
    return NounReader(ScenarioDefaults(fields.nested("defaults")), collector).read(fields), collector


class TestStateKeys:
    """NounReader が状態の鍵の種類と最初の値を、種類を鍵にした地図から読むことを保証する。"""

    def test_choice_and_stock_keys_are_read_with_their_initial_values(self) -> None:
        """選択の鍵は選択肢の一覧、在庫の鍵は上限と補充の間隔 (null は補充しない) を持ち、最初の値を種類に合わせて読む。"""
        read, collector = _read(
            "spots:\n"
            "  hall:\n"
            "    name: 広間\n"
            "    description: 広い。\n"
            "    atmosphere: { lighting: bright }\n"
            "    objects:\n"
            "      well:\n"
            "        name: 井戸\n"
            "        description: 古い井戸。\n"
            "        state_keys:\n"
            "          cover: { kind: { choice: [open, closed] }, initial: closed }\n"
            "          water: { kind: { stock: { capacity: 3, refills_every: null } }, initial: 2 }\n"
        )

        assert collector.flaws == ()
        (well,) = read.objects
        cover, water = well.state_keys
        assert (cover.kind, cover.initial) == (
            ChoiceStateKind(choices=(ChoiceName("open"), ChoiceName("closed"))),
            ChoiceValue(ChoiceName("closed")),
        )
        assert (water.kind, water.initial) == (StockStateKind(Count(3), NoRefill()), StockValue(Count(2)))

    def test_light_source_is_lit_at_the_written_value_of_its_key(self) -> None:
        """カンテラの lights_up は、自分の状態の鍵 lit が真のとき灯る LitWhen になる。"""
        read, collector = _read(
            "item_specs:\n"
            "  lamp:\n"
            "    name: カンテラ\n"
            "    description: 油のカンテラ。\n"
            "    state_keys: { lit: { kind: flag, initial: false } }\n"
            "    lights_up: { key: lit, value: true }\n"
        )

        assert collector.flaws == ()
        assert read.item_specs[0].lights_up == LitWhen(key=StateKeyId("lit"), value=FlagValue(True))

    def test_stock_key_on_an_item_is_a_flaw_at_that_key(self) -> None:
        """品物に在庫の鍵を書くと、その鍵の場所を付けた誤りになり、品物は読めなかったものとして残る。"""
        read, collector = _read(
            "item_specs:\n"
            "  sack:\n"
            "    name: 袋\n"
            "    description: 麻の袋。\n"
            "    state_keys: { grain: { kind: { stock: { capacity: 3, refills_every: null } }, initial: 1 } }\n"
        )

        assert [flaw.location for flaw in collector.flaws] == [DesignLocation("item_spec", "sack", "state_keys.grain")]
        assert ("item_spec", "sack") in read.unreadable


class TestItemLasts:
    """NounReader が品物の lasts を、書いてあれば Lasts、書かなければ LastsIndefinitely として読むことを保証する。"""

    def test_written_lasts_is_read_as_ticks_and_ended_text(self) -> None:
        """lasts に { ticks: 16, ended_text: ... } を書いた品物は、その時間と文を持つ Lasts になる。"""
        read, collector = _read(
            "item_specs:\n"
            "  lamp_flame:\n"
            "    name: カンテラの灯\n"
            "    description: カンテラに灯した火。\n"
            "    lasts: { ticks: 16, ended_text: カンテラの灯が燃え尽きた。 }\n"
        )

        assert collector.flaws == ()
        assert read.item_specs[0].lasts == Lasts(
            ticks=Ticks(16), ended_text=DescriptionText("カンテラの灯が燃え尽きた。")
        )

    def test_item_without_lasts_lasts_indefinitely(self) -> None:
        """lasts を書かない品物は LastsIndefinitely になる。"""
        read, collector = _read("item_specs:\n  rope:\n    name: 縄\n    description: 麻の縄。\n")

        assert collector.flaws == ()
        assert read.item_specs[0].lasts == LastsIndefinitely()

    def test_zero_ticks_is_a_flaw_at_lasts(self) -> None:
        """lasts の ticks に 0 を書くと、lasts の場所を付けた誤りになり、品物は読めなかったものとして残る。"""
        read, collector = _read(
            "item_specs:\n"
            "  lamp_flame:\n"
            "    name: カンテラの灯\n"
            "    description: カンテラに灯した火。\n"
            "    lasts: { ticks: 0, ended_text: カンテラの灯が燃え尽きた。 }\n"
        )

        assert [flaw.location for flaw in collector.flaws] == [DesignLocation("item_spec", "lamp_flame", "lasts")]
        assert ("item_spec", "lamp_flame") in read.unreadable
