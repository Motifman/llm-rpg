"""#363 (実験 #25 ON_FULL ハング) 対策の検証。

全員 outcome 確定後:
- run_scheduled_turns が一切 LLM を回さない
- 行動不可プレイヤーは to_run から除外される
- do_move の 200 tick loop が game_end で break
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestGameEndShortCircuit:
    """ゲーム終了状態なら LLM ターンを一切回さない。"""

    def test_game_ended_run_scheduled_turns_return(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """check_game_end().is_ended=True なら pending を全消して即 return。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        wiring = state.llm_wiring
        trigger = wiring.llm_turn_trigger

        # シナリオの outcome_resolution_config に依存しないよう check_game_end
        # を直接 mock する (= 「全員終了したと runtime が報告した」状態)。
        ended_result = MagicMock()
        ended_result.is_ended = True
        monkeypatch.setattr(state.runtime, "check_game_end", lambda: ended_result)

        # turn を schedule してから run_scheduled_turns を呼ぶ
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        trigger.schedule_turn(pid)
        # LLM client は呼ばれないはずなので、boom stub を入れて検知
        call_count = {"n": 0}

        def _boom(*args, **kwargs):
            call_count["n"] += 1
            raise RuntimeError("LLM should not be invoked after game end")

        wiring.llm_client = MagicMock()
        wiring.llm_client.invoke.side_effect = _boom

        trigger.run_scheduled_turns()

        assert call_count["n"] == 0, (
            "ゲーム終了後に LLM が呼ばれた (Fix 1a が動いていない)"
        )
        # pending / turn_counts もクリアされている
        assert trigger.pending_player_ids == set()


class TestSkipDeadPlayerTurn:
    """死亡 / outcome 確定したプレイヤーの個別 LLM ターンを skip。"""

    def test_outcome_resolved_player_llm(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """outcome resolved player の LLM ターンは 回らない。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        wiring = state.llm_wiring
        trigger = wiring.llm_turn_trigger
        all_players = list(state.runtime.get_player_ids())
        if len(all_players) < 2:
            pytest.skip("scenario has <2 players")

        # 1 人だけ DEAD にする (残りは UNRESOLVED 維持)
        registry = state.runtime._player_outcome_registry
        assert registry is not None
        dead_pid = all_players[0]
        registry.set_outcome(dead_pid, PlayerOutcomeEnum.DEAD)
        # 全体は終了していない (= 残りの player は alive)
        assert state.runtime.check_game_end().is_ended is False

        # 両方 schedule
        for pid in all_players:
            trigger.schedule_turn(pid)

        # 1 人だけ LLM が回るはず。stub で確認。
        called_pids: list[int] = []

        def _stub_invoke(messages, tools, choice, *, metrics_sink=None, reasoning_effort=None):
            # messages 内に player_id を含む system prompt があるとは限らないので、
            # 単純に呼び出し回数だけ確認する
            called_pids.append(len(called_pids))
            return {"name": "wait", "arguments": {"reason": "test"}}

        wiring.llm_client = MagicMock()
        wiring.llm_client.invoke.side_effect = _stub_invoke

        trigger.run_scheduled_turns()

        # DEAD は skip されるので、呼び出しは other 1 人分
        assert len(called_pids) == len(all_players) - 1, (
            f"DEAD player の turn が回ってしまった: {len(called_pids)} calls "
            f"for {len(all_players)} players"
        )

    def test_can_player_act_helper_boundary(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """_can_player_act が outcome / is_down を正しく見る。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        wiring = state.llm_wiring
        trigger = wiring.llm_turn_trigger
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

        # 初期: alive
        assert trigger._can_player_act(pid.value) is True

        # outcome を DEAD にする → 行動不可
        registry = state.runtime._player_outcome_registry
        registry.set_outcome(pid, PlayerOutcomeEnum.DEAD)
        assert trigger._can_player_act(pid.value) is False
