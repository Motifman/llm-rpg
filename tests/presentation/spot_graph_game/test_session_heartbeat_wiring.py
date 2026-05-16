"""脱出セッション作成時に heartbeat がシミュレーションへ配線されることのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


def _scenario_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _heartbeat_observation_count(obs_buffer: object, player_id: PlayerId) -> int:
    get_observations = getattr(obs_buffer, "get_observations")
    entries = list(get_observations(player_id))
    return sum(
        1 for e in entries if (getattr(getattr(e, "output"), "structured") or {}).get("type") == "heartbeat"
    )


class TestSessionHeartbeatWiring:
    """GameRuntimeManager.create_session 後の heartbeat 観測の挙動。"""

    def test_ticks_emit_heartbeat_for_all_spawn_players_when_tick_loop_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """SPOT_GRAPH_TICK_LOOP_ENABLED=false でも tick 進行後にスポーン全員へ heartbeat が入る。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
        mgr = GameRuntimeManager(
            scenarios_dir=_scenario_dir(),
            characters_path=tmp_path / "characters.json",
        )
        char = mgr.create_character(CharacterCreateRequest(name="ヒートビート確認用キャラクター"))
        summary = mgr.create_session(
            SessionCreateRequest(world_id="relay_puzzle_demo", character_ids=[char.id]),
        )
        state = mgr._sessions[summary.session_id]
        runtime = state.runtime
        player_ids = runtime.get_player_ids()
        assert len(player_ids) >= 2

        # post-tick で heartbeat の直後に LLM が走り、_prompt 構築で観測バッファを drain するため
        # 本テストではバッファ上の検証のみにフォーカスし run_scheduled_turns を無効化する。
        monkeypatch.setattr(
            state.llm_wiring.llm_turn_trigger,
            "run_scheduled_turns",
            lambda: None,
        )

        # HeartbeatObservationEmitter は初めの tick で基準だけ記録するため interval+1 進める。
        for _ in range(6):
            runtime.advance_tick()

        buf = runtime._obs_buffer
        assert all(_heartbeat_observation_count(buf, pid) >= 1 for pid in player_ids)
