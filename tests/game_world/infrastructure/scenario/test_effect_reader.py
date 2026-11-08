from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import IsAliveCondition
from ai_rpg_world.game_world.domain.condition.subject import EachPerson
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    FlagStateKind,
    FlagValue,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import NoSmell, Unchanged
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.spot_and_passage_effects import ChangeAtmosphereEffect
from ai_rpg_world.game_world.domain.effect.world_progress_effects import StartGroupDecisionEffect
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, ObjectId, StateKeyId
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.effect_reader import EffectReader
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import read_yaml_document
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import Unreadable, YamlNode
from tests.game_world.support.world_design_for_tests import group_decision, item_spec, nouns, obj, spot

BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
EXILE = group_decision("exile")
BELL_TOWER = replace(
    obj("bell_tower", "hall"),
    state_keys=(
        ObjectStateKeyDeclaration(ObjectId("bell_tower"), StateKeyId("cracked"), FlagStateKind(), FlagValue(False)),
    ),
)
NOUNS = nouns(
    flags=(BELL,),
    spots=(spot("hall"),),
    objects=(BELL_TOWER,),
    item_specs=(item_spec("coin"),),
    group_decisions=(EXILE,),
)
AT = YamlPath.root() / "happenings" / "dusk" / "effect"
EVERYONE_ALIVE = PeopleSelection(where=IsAliveCondition(who=EachPerson(), failure_text=NoText()))


def _reader() -> EffectReader:
    names = DeclaredNames(NOUNS, frozenset(), ScenarioOrigins())
    conditions = ConditionReader(names)

    def voters_and_choices(decision: YamlNode) -> tuple[PeopleSelection, PeopleSelection]:
        assert decision.value == "exile"
        return EVERYONE_ALIVE, EVERYONE_ALIVE

    return EffectReader(names, conditions, voters_and_choices)


def _read(text: str) -> object:
    return _reader().read(YamlNode(read_yaml_document(text).value, AT))


class TestEffectNode:
    """EffectReader が、種類を鍵にした地図の節を効果の型に読むことを保証する。"""

    def test_sequence_of_direct_single_fields(self) -> None:
        """sequence の一覧に、欄が 1 つの raise_flag と、欄の無い no_effect を並べて書ける。"""
        assert _read("sequence: [{ raise_flag: bell_rang }, no_effect]") == SequenceEffect(
            steps=(RaiseFlagEffect(flag=BELL), NoEffect())
        )

    def test_unwritten_atmosphere_field_is_unchanged_and_null_is_absent(self) -> None:
        """change_atmosphere で書かなかった欄は変えず (Unchanged)、null を書いた匂いは無くす (NoSmell)。"""
        effect = _read("change_atmosphere: { spot: hall, lighting: pitch_dark, smell: null }")

        assert isinstance(effect, ChangeAtmosphereEffect)
        assert (effect.lighting, effect.temperature, effect.ambient_sound, effect.smell) == (
            Lighting.PITCH_DARK,
            Unchanged(),
            Unchanged(),
            NoSmell(),
        )

    def test_start_group_decision_takes_voters_and_choices_of_the_decision(self) -> None:
        """start_group_decision: exile は、集団の決定 exile に書いた投票する人と候補の選び方を持つ。"""
        assert _read("start_group_decision: exile") == StartGroupDecisionEffect(
            decision=EXILE, voters=EVERYONE_ALIVE, choices=EVERYONE_ALIVE
        )

    def test_failure_text_is_not_a_field_of_effects(self) -> None:
        """効果の節に failure_text を書くと、種類の鍵が 2 つとして Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _read("raise_flag: bell_rang\nfailure_text: 鳴らない。\n")

        assert raised.value.flaw.location == DesignLocation("happening", "dusk", "effect")


class TestEffectsOnStateKeysOfAnotherKind:
    """物の状態の鍵を数・在庫・書いた文として扱う効果が、種類に合わない鍵を指すと、その効果の場所で Unreadable になることを保証する。"""

    @pytest.mark.parametrize(
        ("text", "kind"),
        [
            ("add_to_object_count: { key: bell_tower.cracked, amount: 1 }", "add_to_object_count"),
            ("subtract_from_object_count: { key: bell_tower.cracked, amount: 1 }", "subtract_from_object_count"),
            ("take_from_object_stock: { key: bell_tower.cracked, amount: 1 }", "take_from_object_stock"),
            ("write_text: { key: bell_tower.cracked, body_argument: message }", "write_text"),
            (
                "deposit_item_to_object: { who: actor, item_spec: coin, key: bell_tower.cracked }",
                "deposit_item_to_object",
            ),
            ("deposit_gold_to_object: { who: actor, amount: 1, key: bell_tower.cracked }", "deposit_gold_to_object"),
        ],
    )
    def test_flag_key_used_as_count_stock_or_text_is_unreadable_at_the_effect(self, text: str, kind: str) -> None:
        """旗の鍵 (鐘楼のひび) に数を足す・在庫を取る・文を書く効果は、素のドメイン例外ではなく、その効果の場所を付けた Unreadable になる。"""
        with pytest.raises(Unreadable) as raised:
            _read(text)

        assert raised.value.flaw.location == DesignLocation("happening", "dusk", f"effect.{kind}")
