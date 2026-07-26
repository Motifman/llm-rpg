"""notify_target の読み込みと、書き間違いの早期検出を保証する。

この宣言が効かないときの症状は「相手が気づかない」で、これは正常な挙動とも
区別がつかない。実行時に気付ける類ではないので、読み込み時に落とす。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _player_interaction(**overrides) -> dict:
    base = {
        "action_name": "poison",
        "display_label": "毒を盛る",
        "witness_policy": "ACTOR_ONLY",
        "preconditions": [{"condition_type": "ALWAYS"}],
        "effects": [{
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 1},
        }],
    }
    base.update(overrides)
    return base


def _load_player_interaction(**overrides):
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    scenario = copy.deepcopy(_minimal_scenario())
    scenario["player_interactions"] = [_player_interaction(**overrides)]
    return ScenarioLoader().load_from_dict(scenario).player_interactions[0]


def _load_object_interaction(**overrides):
    """物体 interaction 側に同じフィールドを書いた場合を読み込む。"""
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    scenario = copy.deepcopy(_minimal_scenario())
    interactions = scenario["spots"][0]["interior"]["objects"][0]["interactions"]
    interactions[0] = {**interactions[0], **overrides}
    return ScenarioLoader().load_from_dict(scenario)


class TestNotifyTargetParsing:
    """対人 interaction では notify_target を宣言できる。"""

    def test_default_is_false(self) -> None:
        """書かなければ False (既存シナリオの挙動は変わらない)。"""
        assert _load_player_interaction().notify_target is False

    def test_declared_flag_is_parsed(self) -> None:
        """notify_target=true がそのまま載る。"""
        assert _load_player_interaction(notify_target=True).notify_target is True

    def test_target_message_is_parsed(self) -> None:
        """対象専用の文面がそのまま載る。"""
        idef = _load_player_interaction(
            notify_target=True,
            target_observation_message="喉の奥が焼けるように熱い。",
        )
        assert idef.target_observation_message == "喉の奥が焼けるように熱い。"

    def test_non_boolean_flag_fails_to_load(self) -> None:
        """notify_target に真偽値以外を書いたら落とす。

        文字列 ``"false"`` は Python では真になるので、黙って通すと
        「切ったつもりが入っている」になる。
        """
        with pytest.raises(ScenarioLoadError):
            _load_player_interaction(notify_target="false")


class TestMessageWithoutFlagIsRejected:
    """文面だけ書いて notify_target を立て忘れた宣言は落とす。"""

    def test_message_without_notify_target_fails_to_load(self) -> None:
        """その文面はどこにも出ないので、読み込み時に落とす。

        ACTOR_ONLY では対象に何も届かないままになり、作者は「書いたのに
        出ない」を実 run で探すことになる。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            _load_player_interaction(
                target_observation_message="喉の奥が焼けるように熱い。"
            )
        assert "notify_target" in str(exc_info.value)


class TestObjectInteractionsRejectTheField:
    """物体 interaction には対象プレイヤーが居ないので書けない。"""

    def test_notify_target_on_object_interaction_fails_to_load(self) -> None:
        """物体側に書いたら落とす (黙って無視すると効かない宣言が残る)。"""
        with pytest.raises(ScenarioLoadError) as exc_info:
            _load_object_interaction(notify_target=True)
        assert "player_interactions" in str(exc_info.value)
