"""いま出していないツールが、呼んでも実行されないことを保証する。

## 出し分けが助言でしかなかった

会議中は ``interact`` も ``travel_to`` もツール一覧に出ない。しかし
dispatch はツール名でハンドラ表を引くだけなので、**LLM が名前を書けば
そのまま動いていた**。

実 run 009 で起きている。アオイが会議の最中に棚卸しを 2 段進めた。

    t=10 会議中の interact: count_supplies   -> success=True
    t=11 会議中の interact: count_supplies_2 -> success=True

本人の思考にもこう出ていた。

    「話し合い中だけど、私の担当の棚卸しをまず進めたい」

会議中に物理的な行為をさせない、という判断が**表示の上でしか守られて
いなかった**。

## 前提条件で弾かない

全 interaction に「会議中は不可」を書いて回ることになる (#860 で潰した形)。
**出していないなら実行もできない**、を 1 か所で守る。

## 「存在しない」とは別の失敗にする

``UNSUPPORTED_TOOL`` は「そんなツールは無い」。こちらは「あるが、いまは
使えない」。同じ文言にすると、会議が終われば使えることが伝わらず、
二度と試さなくなる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)


class _StubClient:
    """LLM は呼ばない。dispatch だけを見る。"""


def _wiring(runtime) -> _WorldLlmWiring:
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=_StubClient(),
    )


def _call(runtime, name: str, arguments: dict):
    return _wiring(runtime)._execute_tool(_MORI, name, arguments, None)


@pytest.fixture()
def in_a_meeting():
    """全員が集まって話し合っている世界。"""
    runtime = create_world_runtime(_DRILL)
    runtime.call_emergency_meeting(_MORI)
    assert "interact" not in {d.name for d in runtime.get_tool_definitions()}
    return runtime


@pytest.fixture()
def free_roam():
    runtime = create_world_runtime(_DRILL)
    assert "interact" in {d.name for d in runtime.get_tool_definitions()}
    return runtime


class TestAToolHiddenByThePhaseCannotRun:
    """フェーズで隠したツールは実行できない。"""

    def test_interacting_during_a_meeting_is_refused(self, in_a_meeting) -> None:
        """会議中の interact が拒否される。

        **これが実 run 009 で通っていた形。** 会議の最中に作業が進んだ。
        """
        result = _call(
            in_a_meeting,
            "interact",
            {"target_label": "気象記録簿", "action_name": "log_weather"},
        )

        assert result.success is False
        assert result.error_code == "TOOL_NOT_OFFERED_NOW"

    def test_travelling_during_a_meeting_is_refused(self, in_a_meeting) -> None:
        """会議中の移動も拒否される。

        interact だけを塞いでも、別のツールで抜けられれば同じこと。
        """
        result = _call(in_a_meeting, "travel_to", {"destination_label": "物資庫"})

        assert result.error_code == "TOOL_NOT_OFFERED_NOW"

    def test_speaking_during_a_meeting_still_works(self, in_a_meeting) -> None:
        """会議中でも話せる。

        **塞ぎすぎると会議が成立しない。** 「全部拒否」でもテストは通って
        しまうので、通る側を必ず一緒に見る。
        """
        result = _call(in_a_meeting, "speak", {"channel": "say", "content": "誰だ"})

        assert result.error_code != "TOOL_NOT_OFFERED_NOW"


class TestAToolDisabledByTheScenarioCannotRun:
    """シナリオが落としたツールも実行できない。"""

    def test_a_disabled_tool_is_refused(self, free_roam) -> None:
        """station_drill が落とした tend_to_player が拒否される。

        フェーズ軸とは別の軸。**どちらも同じ出口で守る**ことをここで確かめる。
        """
        result = _call(free_roam, "tend_to_player", {"target_player_label": "セナ"})

        assert result.error_code == "TOOL_NOT_OFFERED_NOW"


class TestTheRefusalIsDistinctFromNotExisting:
    """「いま使えない」と「存在しない」を区別する。"""

    def test_an_unknown_tool_still_says_unsupported(self, free_roam) -> None:
        """本当に存在しないツールは今までどおり UNSUPPORTED_TOOL。

        混ぜると、会議が終われば使えることが伝わらず二度と試さなくなる。
        逆に、綴り間違いを「いまは使えない」と言われても直せない。
        """
        result = _call(free_roam, "teleport_to_moon", {})

        assert result.error_code == "UNSUPPORTED_TOOL"

    def test_the_refusal_says_it_may_come_back(self, in_a_meeting) -> None:
        """断り文句が「いまは」であることを伝える。"""
        result = _call(
            in_a_meeting, "interact", {"target_label": "x", "action_name": "y"}
        )

        assert "いま" in result.message

    def test_the_refusal_wakes_the_agent_again(self, in_a_meeting) -> None:
        """断られた本人が次の tick に起きる。

        起きないと、断られたことを読めないまま黙って止まる。
        """
        result = _call(
            in_a_meeting, "interact", {"target_label": "x", "action_name": "y"}
        )

        assert result.should_reschedule is True


class TestNothingIsBlockedDuringFreeRoam:
    """自由時間の挙動は変わらない。"""

    @pytest.mark.parametrize("name", ["interact", "travel_to", "explore", "speak"])
    def test_ordinary_tools_pass_the_gate(self, free_roam, name) -> None:
        """普段使うツールは門で止まらない。

        **既存 run への影響がゼロであること**をここで担保する。引数不足で
        失敗するのは構わない。見たいのは `TOOL_NOT_OFFERED_NOW` にならない
        ことだけ。
        """
        result = _call(free_roam, name, {})

        assert result.error_code != "TOOL_NOT_OFFERED_NOW"
