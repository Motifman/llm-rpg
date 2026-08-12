"""InteractionEffect.target のパースと検証を保証する。

対人インタラクション基盤の第一歩。効果の適用先を「行為者」と「対象プレイヤー」の
どちらにするかをシナリオが宣言できるようにする
(docs/memory_system/interpersonal_interaction_design.md)。

この PR の時点では ``TARGET_PLAYER`` を宣言しても効果を対象へ適用する経路が
まだ無い。書けるのに何も起きない状態を残さないため、**宣言できない文脈で
書かれていたら読み込み時に落とす**ところまでを本 PR に含める。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _minimal() -> dict:
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    return copy.deepcopy(_minimal_scenario())


def _scenario_with_object_effect(effect: dict) -> dict:
    """最小シナリオの spot object に interaction を 1 つ足して返す。"""
    scenario = _minimal()
    spot = scenario["spots"][0]
    interior = spot.setdefault("interior", {})
    interior.setdefault("objects", []).append(
        {
            "id": "test_object",
            "name": "試験用オブジェクト",
            "description": "d",
            "interactions": [
                {
                    "action_name": "poke",
                    "display_label": "つつく",
                    "effects": [effect],
                }
            ],
        }
    )
    return scenario


def _first_effect(scenario: dict):
    result = ScenarioLoader().load_from_dict(scenario)
    for interior in result.interiors.values():
        for obj in interior.objects:
            for idef in obj.interactions:
                if idef.action_name == "poke":
                    return idef.effects[0]
    raise AssertionError("poke interaction が見つからない")


class TestEffectTargetParsing:
    """effects[].target がパースされ、既定は行為者になる。"""

    def test_target_defaults_to_actor(self) -> None:
        """target を書かない効果は EffectTarget.ACTOR になる (既存シナリオの挙動不変)。"""
        effect = _first_effect(
            _scenario_with_object_effect(
                {"effect_type": "APPLY_DAMAGE", "parameters": {"damage": 1}}
            )
        )
        assert effect.target is EffectTarget.ACTOR

    def test_target_player_is_parsed(self) -> None:
        """target に TARGET_PLAYER を書くと EffectTarget.TARGET_PLAYER になる。

        例に使うのは配線済みの効果でなければならない。未配線の効果
        (APPLY_DAMAGE 等) は宣言しても行為者に効いてしまうので、loader が
        別途落とす。
        """
        effect = _first_effect(
            _scenario_with_object_effect(
                {
                    "effect_type": "REMOVE_ITEM",
                    "target": "TARGET_PLAYER",
                    "parameters": {"item_spec_id": "iron_sword"},
                }
            )
        )
        assert effect.target is EffectTarget.TARGET_PLAYER

    def test_unknown_target_value_fails_to_load(self) -> None:
        """未知の target 値は ScenarioLoadError になり、綴り間違いに気づける。

        visibility の既存パースのように黙って既定へ倒すと、"TARGET_PLAYERS" の
        typo が ACTOR に落ちて **自分に致死ダメージ** が入る。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            _first_effect(
                _scenario_with_object_effect(
                    {
                        "effect_type": "APPLY_DAMAGE",
                        "target": "TARGET_PLAYERS",
                        "parameters": {"damage": 1},
                    }
                )
            )
        assert "target" in str(exc_info.value)


class TestEffectTargetRejectedForUnsupportedEffects:
    """対象を取れない効果に TARGET_PLAYER を書くと読み込み時に落ちる。"""

    def test_combine_items_rejects_target_player(self) -> None:
        """COMBINE_ITEMS に TARGET_PLAYER を書くと ScenarioLoadError になる。

        素材を合成する効果に「相手を対象に」は意味を持たない。黙って ACTOR と
        して動かすと、作者は対象へ効いたつもりのまま気づけない。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            _first_effect(
                _scenario_with_object_effect(
                    {
                        "effect_type": "COMBINE_ITEMS",
                        "target": "TARGET_PLAYER",
                        "parameters": {},
                    }
                )
            )
        assert "COMBINE_ITEMS" in str(exc_info.value)

    def test_change_passage_state_rejects_target_player(self) -> None:
        """通路の状態変更のように世界へ効く効果は TARGET_PLAYER を受け付けない。"""
        with pytest.raises(ScenarioLoadError) as exc_info:
            _first_effect(
                _scenario_with_object_effect(
                    {
                        "effect_type": "CHANGE_PASSAGE_STATE",
                        "target": "TARGET_PLAYER",
                        "parameters": {
                            "target_connection": "conn_a_b",
                            "new_state": "OPEN",
                        },
                    }
                )
            )
        assert "CHANGE_PASSAGE_STATE" in str(exc_info.value)

    def test_show_message_rejects_target_player(self) -> None:
        """メッセージ表示のように誰か 1 人に効くわけでない効果も受け付けない。"""
        with pytest.raises(ScenarioLoadError) as exc_info:
            _first_effect(
                _scenario_with_object_effect(
                    {
                        "effect_type": "SHOW_MESSAGE",
                        "target": "TARGET_PLAYER",
                        "parameters": {"message": "x"},
                    }
                )
            )
        assert "SHOW_MESSAGE" in str(exc_info.value)


class TestEffectTargetRejectedWhereActorIsAbsent:
    """行為者が存在しない文脈で TARGET_PLAYER を書くと読み込み時に落ちる。

    scenario_events と synchronized_action_groups には行為者が居ない。誰を
    対象にするのか決まらないので、書けるのに何も起きない状態を作らない。
    """

    def test_scenario_event_effect_rejects_target_player(self) -> None:
        """scenario_events の effects に TARGET_PLAYER を書くと ScenarioLoadError。"""
        scenario = _minimal()
        scenario.setdefault("scenario_events", []).append(
            {
                "id": "ev",
                "trigger": "ON_TICK",
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 1}],
                "effects": [
                    {
                        "effect_type": "APPLY_DAMAGE",
                        "target": "TARGET_PLAYER",
                        "parameters": {"damage": 1},
                    }
                ],
            }
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(scenario)
        assert "scenario_event" in str(exc_info.value)

    def test_scenario_event_rejects_recording_an_actors_tick(self) -> None:
        """行為者のいない scenario_event は RECORD_PLAYER_STATE_TICK を受け付けない。"""
        scenario = _minimal()
        scenario.setdefault("scenario_events", []).append(
            {
                "id": "ev",
                "trigger": "ON_TICK",
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 1}],
                "effects": [
                    {
                        "effect_type": "RECORD_PLAYER_STATE_TICK",
                        "parameters": {"state_key": "triggered_at_tick"},
                    }
                ],
            }
        )

        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(scenario)

        assert "scenario_event" in str(exc_info.value)
        assert "RECORD_PLAYER_STATE_TICK" in str(exc_info.value)

    def test_synchronized_action_group_rejects_target_player(self) -> None:
        """synchronized_action_groups の on_complete に TARGET_PLAYER を書くと ScenarioLoadError。"""
        scenario = _minimal()
        scenario.setdefault("synchronized_action_groups", []).append(
            {
                "group_id": "g1",
                "required_action_names": ["a", "b"],
                "window_ticks": 2,
                "on_complete": [
                    {
                        "effect_type": "APPLY_DAMAGE",
                        "target": "TARGET_PLAYER",
                        "parameters": {"damage": 1},
                    }
                ],
            }
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(scenario)
        assert "synchronized_action_group" in str(exc_info.value)
