"""場所条件 (SPOT_LIGHTING_IS / AT_SPOT_IS) の読み込みを保証する。

これらは「暗い場所ならどこでも襲える」「特定の部屋でだけ使える」を 1 回の
宣言で書くための前提条件である
(docs/memory_system/interpersonal_interaction_design.md §3.2)。

読み込み時に落とすものが多いのは、この種の書き間違いが実行時には
「なぜか一度も成功しない」としてしか現れないため。条件が常に不成立でも
シナリオ作者の failure_message が返るので、原因が文言に隠れる。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_condition(cond: dict) -> dict:
    """最小シナリオの player_interactions に条件 1 つを載せる。"""
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    scenario = copy.deepcopy(_minimal_scenario())
    scenario["player_interactions"] = [{
        "action_name": "strike_down",
        "display_label": "背後から襲う",
        "preconditions": [cond],
        "effects": [{
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 999},
        }],
    }]
    return scenario


def _load_condition(cond: dict):
    result = ScenarioLoader().load_from_dict(_scenario_with_condition(cond))
    return result.player_interactions[0].preconditions[0]


class TestSpotLightingCondition:
    """SPOT_LIGHTING_IS{_NOT} の required_lighting をパースする。"""

    def test_lighting_value_is_parsed(self) -> None:
        """required_lighting がそのまま条件に載る。"""
        cond = _load_condition({
            "condition_type": "SPOT_LIGHTING_IS",
            "required_lighting": "DARK",
            "failure_message": "明るすぎる。",
        })
        assert cond.condition_type is InteractionConditionTypeEnum.SPOT_LIGHTING_IS
        assert cond.required_lighting == "DARK"

    def test_unknown_lighting_value_fails_to_load(self) -> None:
        """LightingEnum に無い値は読み込み時に落とす。

        実行時に落とすと「照明が一致しないので不成立」と区別がつかず、
        タイポが失敗文の裏に隠れる。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            _load_condition({
                "condition_type": "SPOT_LIGHTING_IS",
                "required_lighting": "PITCH_DARK",  # 正しくは PITCH_BLACK
            })
        assert "PITCH_DARK" in str(exc_info.value)

    def test_missing_lighting_value_fails_to_load(self) -> None:
        """required_lighting の無い SPOT_LIGHTING_IS は落とす (常に不成立になる)。"""
        with pytest.raises(ScenarioLoadError):
            _load_condition({"condition_type": "SPOT_LIGHTING_IS"})

    def test_lighting_on_unrelated_condition_fails_to_load(self) -> None:
        """関係ない条件に required_lighting を書いたら落とす。

        黙って無視すると「暗所限定にしたつもりの行為」がどこでも通る。
        """
        with pytest.raises(ScenarioLoadError):
            _load_condition({
                "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
                "required_lighting": "DARK",
            })


class TestAtSpotCondition:
    """AT_SPOT_IS{_NOT} の required_spot をシナリオ ID から解決する。"""

    def test_spot_reference_is_resolved_to_spot_id(self) -> None:
        """required_spot の文字列 ID が SpotId に解決される。"""
        cond = _load_condition({
            "condition_type": "AT_SPOT_IS",
            "required_spot": "room_a",
            "failure_message": "ここではできない。",
        })
        assert cond.condition_type is InteractionConditionTypeEnum.AT_SPOT_IS
        assert cond.required_spot_id is not None
        assert int(cond.required_spot_id.value) > 0

    def test_unknown_spot_reference_fails_to_load(self) -> None:
        """存在しないスポット ID は ScenarioLoadError で落とす。

        同じ「シナリオの書き間違い」なのに例外型が条件ごとに変わると、
        呼び出し側の except が漏れる。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            _load_condition({
                "condition_type": "AT_SPOT_IS",
                "required_spot": "room_zzz",
            })
        assert "room_zzz" in str(exc_info.value)

    def test_missing_spot_reference_fails_to_load(self) -> None:
        """required_spot の無い AT_SPOT_IS は落とす (常に不成立になる)。"""
        with pytest.raises(ScenarioLoadError):
            _load_condition({"condition_type": "AT_SPOT_IS"})

    def test_spot_on_unrelated_condition_fails_to_load(self) -> None:
        """関係ない条件に required_spot を書いたら落とす。"""
        with pytest.raises(ScenarioLoadError):
            _load_condition({
                "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
                "required_spot": "room_a",
            })


class TestTargetPlayerStateCondition:
    """TARGET_PLAYER_STATE_IS は required_state を必要とする。"""

    def test_required_state_is_parsed(self) -> None:
        """required_state がそのまま条件に載る。"""
        cond = _load_condition({
            "condition_type": "TARGET_PLAYER_STATE_IS",
            "required_state": {"role": "crew"},
        })
        assert cond.required_state == {"role": "crew"}

    def test_missing_required_state_fails_to_load(self) -> None:
        """required_state の無い TARGET_PLAYER_STATE_IS は落とす。"""
        with pytest.raises(ScenarioLoadError):
            _load_condition({"condition_type": "TARGET_PLAYER_STATE_IS"})
