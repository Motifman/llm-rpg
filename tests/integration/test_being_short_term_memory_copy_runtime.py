"""本番の runtime で、今の短期記憶に入った出来事が Being 側の短期記憶にも並べて書かれ、プロンプトは変わらないことを保証する (#1824、design_decisions D1824-7)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_WAIT
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import OwnActionResult
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.judgment_helpers import ScriptedJudgmentPort
from tests.trace_helpers import RecordingTraceRecorder

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_ME = PlayerId(1)


def _game(*, copy: bool = True) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    runtime = create_world_runtime(_DRILL, config=ResolvedLlmRuntimeConfig.for_tests())
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    if not copy:
        runtime._recent_event_store.remove_append_listener(runtime._being_short_term_memory_copy.on_appended)
        runtime._being_short_term_memory_copy = None
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(
            {"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {"inner_thought": "様子を見る"}}
        ),
        typed_judgment_port=ScriptedJudgmentPort(),
    )
    return runtime, wiring, recorder


def _turn(wiring: _WorldLlmWiring) -> Any:
    return wiring.run_phase_b(wiring.run_phase_a(_ME))


class TestCopyInTheRuntime:
    """create_world_runtime が組んだ写す側が、本番の手番の流れで Being 側の短期記憶を書くことを保証する。"""

    def test_each_turn_result_is_copied_with_its_move_and_turn_number(self) -> None:
        """2 回待つと、Being 側の短期記憶に、待つ 1 手と対になった自分の行動の結果が、時計の番号 1 と 2 で入る。"""
        runtime, wiring, recorder = _game()

        _turn(wiring)
        _turn(wiring)

        being_id = runtime._acting_being_for(_ME).being_id
        own_results = [
            e for e in runtime._being_short_term_memory_store.get(being_id).events
            if isinstance(e.observation.route, OwnActionResult)
        ]
        assert [(e.turn, e.move.tool_name, e.move.inner_thought) for e in own_results] == [
            (1, TOOL_NAME_SPOT_GRAPH_WAIT, "様子を見る"),
            (2, TOOL_NAME_SPOT_GRAPH_WAIT, "様子を見る"),
        ]
        assert runtime._memory_turn_clock.current_turn(being_id) == 2
        assert [
            p for p in recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED)
            if p["reason"] in {"memory_rule", "contract_violation", "unexpected_error"}
        ] == []

    def test_observation_gets_the_number_of_the_move_that_sees_it(self) -> None:
        """手番の前に預かった観測は、プロンプトを組むときに取り出され、それを見る 1 手と同じ番号になる。出来事は届いた順に [観測 1, 結果 1, 観測 2, 結果 2] と並ぶ。"""
        runtime, wiring, _ = _game()

        for minute, prose in ((1, "鐘が鳴った"), (2, "扉の向こうで足音がした")):
            runtime._obs_buffer.append(
                _ME,
                ObservationEntry(occurred_at=datetime(2026, 6, 1, 0, minute, tzinfo=timezone.utc), game_time_label=f"深夜 0:0{minute}", output=ObservationOutput(prose=prose, structured={"type": "distant_cue_appeared"})),
            )
            _turn(wiring)

        being_id = runtime._acting_being_for(_ME).being_id
        events = runtime._being_short_term_memory_store.get(being_id).events
        assert [(e.turn, type(e.observation.route).__name__, e.observation.body.split("\n")[0]) for e in events] == [
            (1, "SeenOrHeard", "鐘が鳴った"),
            (1, "OwnActionResult", "[行動] その場で待機した → [結果] しばらく行動を控えて、様子を見た"),
            (2, "SeenOrHeard", "扉の向こうで足音がした"),
            (2, "OwnActionResult", "[行動] その場で待機した → [結果] しばらく行動を控えて、様子を見た"),
        ]

    def test_copying_does_not_change_the_prompt(self) -> None:
        """写す側があってもなくても、同じ 2 手のあとに組むプロンプトは同じ文になる。"""
        with_copy, with_copy_wiring, _ = _game(copy=True)
        without_copy, without_copy_wiring, _ = _game(copy=False)
        for wiring in (with_copy_wiring, without_copy_wiring):
            _turn(wiring)
            _turn(wiring)

        assert with_copy.build_full_prompt(_ME)["messages"] == without_copy.build_full_prompt(_ME)["messages"]
