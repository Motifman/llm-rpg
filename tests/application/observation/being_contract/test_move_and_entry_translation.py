"""ゲームのツール呼び出しとシナリオを、エージェントの 1 手と環境に入るときの取り決めへ変換する規則を保証する。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.observation.being_contract import (
    agent_move_from_tool_call,
    environment_entry_for_player,
)
from ai_rpg_world.being.contract import EnvironmentEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestAgentMoveFromToolCall:
    """ツール呼び出しの引数から、予期・内心・目的の更新を 1 手の欄へ取り出す規則を保証する。"""

    def test_subjective_arguments_move_to_their_own_fields(self) -> None:
        """expected_result・inner_thought・goal_update は 1 手の欄へ移り、引数からは消える。"""
        move = agent_move_from_tool_call(
            "travel_to",
            {
                "destination_label": "通信室",
                "expected_result": "通信室に着く",
                "inner_thought": "急ごう",
                "goal_update": "計器を直す",
            },
            call_id="call-1",
        )

        assert move.call_id == "call-1"
        assert move.tool_name == "travel_to"
        assert dict(move.arguments) == {"destination_label": "通信室"}
        assert move.expectation == "通信室に着く"
        assert move.inner_thought == "急ごう"
        assert move.goal_update == "計器を直す"

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_subjective_argument_becomes_absent(self, blank: Any) -> None:
        """主観の引数が null や空文字なら、1 手の欄は None になる。"""
        move = agent_move_from_tool_call(
            "wait", {"expected_result": blank, "goal_update": blank}, call_id="call-1"
        )

        assert move.expectation is None
        assert move.goal_update is None
        assert dict(move.arguments) == {}

    def test_non_text_subjective_argument_is_rejected(self) -> None:
        """主観の引数に文字列でも null でもない値が来たら、黙って捨てずに ValueError を投げる。"""
        with pytest.raises(ValueError):
            agent_move_from_tool_call("wait", {"inner_thought": 3}, call_id="call-1")


def _scenario(*, objective: str | None, shared_objective: str) -> Any:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            title="無人島サバイバル", llm_objective_text=shared_objective
        ),
        player_spawns=(
            SimpleNamespace(player_id=1, name="エイダ", objective=objective),
            SimpleNamespace(player_id=2, name="リオ", objective=None),
        ),
    )


class TestEnvironmentEntryForPlayer:
    """シナリオから、そのプレイヤーが環境に入るときの取り決めを作る規則を保証する。"""

    def test_player_objective_is_the_imposed_goal(self) -> None:
        """プレイヤー個別の目的があれば、それが環境の課す目的になる。"""
        entry = environment_entry_for_player(
            _scenario(objective="全員を救助させる", shared_objective="島から脱出する"),
            PlayerId.create(1),
        )

        assert entry == EnvironmentEntry(
            environment_name="無人島サバイバル",
            self_name="エイダ",
            imposed_goal="全員を救助させる",
        )

    def test_shared_objective_is_used_without_player_objective(self) -> None:
        """個別の目的が無ければ、シナリオ共通の目的が環境の課す目的になる。"""
        entry = environment_entry_for_player(
            _scenario(objective=None, shared_objective="島から脱出する"),
            PlayerId.create(2),
        )

        assert entry.self_name == "リオ"
        assert entry.imposed_goal == "島から脱出する"

    def test_no_objective_means_no_imposed_goal(self) -> None:
        """個別の目的も共通の目的も無ければ、環境は目的を課さない。"""
        entry = environment_entry_for_player(
            _scenario(objective=None, shared_objective=""), PlayerId.create(2)
        )

        assert entry.imposed_goal is None

    def test_unknown_player_is_rejected(self) -> None:
        """シナリオに居ないプレイヤーを渡すと LookupError を投げる。"""
        with pytest.raises(LookupError):
            environment_entry_for_player(
                _scenario(objective=None, shared_objective=""), PlayerId.create(9)
            )
