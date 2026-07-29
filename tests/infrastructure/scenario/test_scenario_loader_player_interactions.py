"""シナリオ直下 player_interactions のパースを保証する。

対人行為 (奪う・手当てする・印を刻む) の定義はシナリオに 1 回だけ書き、
「どこで使えるか」は前提条件で表現する。spot object にぶら下げると同じ行為を
複数の場所で使うのに複数回定義が要り、「暗い場所ならどこでも」のような動的な
条件も書けない (docs/memory_system/interpersonal_interaction_design.md §3.2)。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_player_interactions(*defs: dict) -> dict:
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    scenario = copy.deepcopy(_minimal_scenario())
    scenario["player_interactions"] = list(defs)
    return scenario


def _take_def(**overrides) -> dict:
    """「倒れた相手から 1 つ奪う」の完全形。

    fixture であると同時に、シナリオ作者がそのまま写せる canonical な例に
    しておく。奪うは **2 つの効果の対**で書く — 対象から REMOVE_ITEM し、
    行為者へ GIVE_ITEM する。片方だけだと物が消えるか湧くかになる。

    品目は ``interaction_parameters`` から実行時に決める。参照するキーは
    条件が ``item_spec_id_parameter_key``、効果が
    ``parameters.item_spec_id_parameter`` で、どちらも同じキーを指す。LLM は
    品目を**名前**で渡し (``parameters={"item": "太い流木"}``)、名前から
    spec id への解決は application 層が対象のインベントリを見て行う。
    """
    base = {
        "action_name": "loot_from_downed",
        "display_label": "持ち物を奪う",
        "preconditions": [
            {
                "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
                "failure_message": "相手は起きている。奪えない。",
            },
            {
                "condition_type": "TARGET_HAS_ITEM",
                "item_spec_id_parameter_key": "item_spec_id",
                "failure_message": "相手はそれを持っていない。",
            },
        ],
        "effects": [
            {
                "effect_type": "REMOVE_ITEM",
                "target": "TARGET_PLAYER",
                "parameters": {"item_spec_id_parameter": "item_spec_id"},
            },
            {
                "effect_type": "GIVE_ITEM",
                "target": "ACTOR",
                "parameters": {"item_spec_id_parameter": "item_spec_id"},
            },
        ],
    }
    base.update(overrides)
    return base


class TestPlayerInteractionsParsing:
    """シナリオ直下の player_interactions が読み込まれる。"""

    def test_absent_key_yields_empty_tuple(self) -> None:
        """player_interactions を書かないシナリオでは空タプルになる (既存シナリオは不変)。"""
        from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

        result = ScenarioLoader().load_from_dict(copy.deepcopy(_minimal_scenario()))
        assert result.player_interactions == ()

    def test_action_name_and_label_are_parsed(self) -> None:
        """action_name と display_label がそのまま載る。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player_interactions(_take_def())
        )
        assert len(result.player_interactions) == 1
        idef = result.player_interactions[0]
        assert idef.action_name == "loot_from_downed"
        assert idef.display_label == "持ち物を奪う"

    def test_effect_target_player_is_allowed_here(self) -> None:
        """player_interactions の効果には target=TARGET_PLAYER を書ける。

        行為者と対象がどちらも存在する唯一の文脈なので、scenario_event などと
        違って拒否しない。
        """
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player_interactions(_take_def())
        )
        effect = result.player_interactions[0].effects[0]
        assert effect.target is EffectTarget.TARGET_PLAYER

    def test_duplicate_action_name_fails_to_load(self) -> None:
        """同じ action_name を 2 つ書くと ScenarioLoadError になる。

        LLM は action_name で行為を指定するので、重複すると「どちらが実行されたか
        分からない」状態になる。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(_take_def(), _take_def())
            )
        assert "loot_from_downed" in str(exc_info.value)

    def test_missing_action_name_fails_to_load(self) -> None:
        """action_name の無い定義は ScenarioLoadError になる。"""
        broken = _take_def()
        del broken["action_name"]
        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(broken)
            )

    def test_effect_without_target_player_fails_to_load(self) -> None:
        """対象への効果を 1 つも持たない定義は ScenarioLoadError になる。

        player_interactions は「相手に何かをする」ための宣言なので、行為者にしか
        効かない定義は書き間違いとみなす。放置すると「相手を選んだのに自分に
        効く」という最も分かりにくい失敗になる。
        """
        actor_only = _take_def(
            effects=[
                {"effect_type": "APPLY_DAMAGE", "parameters": {"damage": 1}}
            ]
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(actor_only)
            )
        assert "TARGET_PLAYER" in str(exc_info.value)


class TestUnwiredTargetPlayerEffectsAreRejected:
    """対象に効くと宣言できても実際には効かない効果は、起動時に落とす。

    ``EffectTarget`` は 8 種の効果に ``TARGET_PLAYER`` を許しているが、実際に
    対象へ適用されるのはアイテムの授受だけである。ダメージ等はバケットが
    行為者ぶんしかないので、宣言しても**行為者に効く**。これは「相手を刺した
    つもりが自分が傷ついた」という、成功として返る最悪の誤動作になる。

    配線が済むまでは loader で落とす。宣言できるのに効かない状態を残すと、
    実 run で初めて気付くことになる。
    """

    # APPLY_DAMAGE は対人ダメージ PR で配線したのでここから外した。
    # 残っているのは、宣言しても対象ではなく行為者に効いてしまうもの。
    @pytest.mark.parametrize(
        "effect_type",
        ["SATISFY_NEED", "CHANGE_PLAYER_STATE", "APPLY_STATUS_EFFECT"],
    )
    def test_unwired_effect_type_is_rejected(self, effect_type: str) -> None:
        """未配線の効果に target=TARGET_PLAYER を書くと ScenarioLoadError。"""
        scenario = _scenario_with_player_interactions(
            _take_def(
                effects=[
                    {
                        "effect_type": effect_type,
                        "target": "TARGET_PLAYER",
                        "parameters": {},
                    }
                ]
            )
        )
        with pytest.raises(ScenarioLoadError) as e:
            ScenarioLoader().load_from_dict(scenario)
        assert effect_type in str(e.value)

    def test_item_transfer_to_target_is_still_allowed(self) -> None:
        """配線済みのアイテム授受は、これまでどおり宣言できる。"""
        scenario = _scenario_with_player_interactions(
            _take_def(
                effects=[
                    {
                        "effect_type": "REMOVE_ITEM",
                        "target": "TARGET_PLAYER",
                        "parameters": {"item_spec_id_parameter": "item_spec_id"},
                    }
                ]
            )
        )
        result = ScenarioLoader().load_from_dict(scenario)
        assert result.player_interactions[0].action_name == "loot_from_downed"


class TestTargetHasItemRequiresAnItemSource:
    """判定する品目を書き忘れた対象所持条件は、読み込み時に落とす。

    ``required_item`` も ``item_spec_id_parameter_key`` も無いと、条件は永久に
    不成立になり interaction が黙って使えなくなる。実 run で「なぜか一度も
    成功しない」として初めて気付くことになる。
    """

    def test_condition_without_any_item_source_fails_to_load(self) -> None:
        """どちらも書かないと ScenarioLoadError。"""
        scenario = _scenario_with_player_interactions(
            _take_def(
                preconditions=[
                    {
                        "condition_type": "TARGET_HAS_ITEM",
                        "failure_message": "相手はそれを持っていない。",
                    }
                ]
            )
        )
        with pytest.raises(ScenarioLoadError) as e:
            ScenarioLoader().load_from_dict(scenario)
        assert "TARGET_HAS_ITEM" in str(e.value)

    def test_runtime_key_alone_is_enough(self) -> None:
        """``item_spec_id_parameter_key`` だけでも読み込める。"""
        scenario = _scenario_with_player_interactions(
            _take_def(
                preconditions=[
                    {
                        "condition_type": "TARGET_HAS_ITEM",
                        "item_spec_id_parameter_key": "item_spec_id",
                    }
                ]
            )
        )
        result = ScenarioLoader().load_from_dict(scenario)
        assert result.player_interactions[0].action_name == "loot_from_downed"
