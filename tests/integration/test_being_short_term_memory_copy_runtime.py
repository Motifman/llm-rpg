"""本番の runtime で、ゲームの出来事が Being 側の短期記憶に書かれ、プロンプトがそこから作られることを保証する (#1824、design_decisions D1824-7)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.world_llm_turn.types import WORLD_ACTION_HESITATION
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS, recent_events_text
from ai_rpg_world.being.domain.short_term_memory import (
    RECENT_TURNS,
    Attempt,
    Backstory,
    Lapse,
    MemoryOperationOutcome,
    Perception,
    ShortTermMemory,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.judgment_helpers import ScriptedJudgmentPort
from tests.trace_helpers import RecordingTraceRecorder

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_ME = PlayerId(1)


_WAIT = {"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {"inner_thought": "様子を見る"}}


def _game(
    *, copy: bool = True, tool_call: dict[str, Any] | None = _WAIT
) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
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
        llm_client=StubLlmClient(tool_call),
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
            e for e in runtime._being_short_term_memory_store.get(being_id).experiences if isinstance(e, Attempt)
        ]
        assert [(e.turn, e.move.tool_name, e.move.inner_thought) for e in own_results] == [
            (1, TOOL_NAME_SPOT_GRAPH_WAIT, "様子を見る"),
            (2, TOOL_NAME_SPOT_GRAPH_WAIT, "様子を見る"),
        ]
        assert runtime._memory_turn_clock.current_turn(being_id) == 2
        assert [
            p
            for p in recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED)
            if p["reason"] in {"memory_rule", "contract_violation", "unexpected_error"}
        ] == []

    def test_observation_gets_the_number_of_the_move_that_sees_it(self) -> None:
        """手番の前に預かった観測は、プロンプトを組むときに取り出され、それを見る 1 手と同じ番号になる。出来事は届いた順に [観測 1, 結果 1, 観測 2, 結果 2] と並ぶ。"""
        runtime, wiring, _ = _game()

        for minute, prose in ((1, "鐘が鳴った"), (2, "扉の向こうで足音がした")):
            runtime._obs_buffer.append(
                _ME,
                ObservationEntry(
                    occurred_at=datetime(2026, 6, 1, 0, minute, tzinfo=timezone.utc),
                    game_time_label=f"深夜 0:0{minute}",
                    output=ObservationOutput(prose=prose, structured={"type": "distant_cue_appeared"}),
                ),
            )
            _turn(wiring)

        being_id = runtime._acting_being_for(_ME).being_id
        experiences = runtime._being_short_term_memory_store.get(being_id).experiences
        bodies = [
            (
                e.turn,
                type(e).__name__,
                (e.observation if isinstance(e, Perception) else e.result.observation).body.split("\n")[0],
            )
            for e in experiences
        ]
        assert bodies == [
            (1, "Perception", "鐘が鳴った"),
            (1, "Attempt", "[行動] その場で待機した → [結果] しばらく行動を控えて、様子を見た"),
            (2, "Perception", "扉の向こうで足音がした"),
            (2, "Attempt", "[行動] その場で待機した → [結果] しばらく行動を控えて、様子を見た"),
        ]

    def test_without_copying_the_prompt_shows_no_recent_events(self) -> None:
        """`PlayerShortTermMemoryCopy` を配線しないと、同じ 2 手のあとでも【直近の出来事】は「（直近の出来事はありません）」になる。プロンプトの出来事は、この写す処理を通ってしか入らない。"""
        with_copy, with_copy_wiring, _ = _game(copy=True)
        without_copy, without_copy_wiring, _ = _game(copy=False)
        for wiring in (with_copy_wiring, without_copy_wiring):
            _turn(wiring)
            _turn(wiring)

        assert _recent_events_section(_user_content(without_copy)) == NO_RECENT_EVENTS
        assert "しばらく行動を控えて、様子を見た" in _user_content(with_copy)


class TestMemoryOperationsAndLapsesInTheRuntime:
    """本番の手番の流れで、記憶の道具の 1 手と、1 手を出せなかったことが Being 側の短期記憶に入ることを保証する (design_decisions D1824-9)。"""

    def test_memory_tool_move_is_kept_with_its_memory_operation_result(self) -> None:
        """エピソードを思い出す 1 手を選ぶと、その 1 手と組の Attempt が、記憶の結果を持って番号 1 で入る。写せなかった trace は残らない。"""
        runtime, wiring, recorder = _game(
            tool_call={
                "name": TOOL_NAME_EPISODE_RECALL,
                "arguments": {"handles": ["鍵のこと"], "inner_thought": "思い出す"},
            }
        )

        _turn(wiring)

        being_id = runtime._acting_being_for(_ME).being_id
        (attempt,) = [
            e for e in runtime._being_short_term_memory_store.get(being_id).experiences if isinstance(e, Attempt)
        ]
        assert (attempt.turn, attempt.move.tool_name) == (1, TOOL_NAME_EPISODE_RECALL)
        assert isinstance(attempt.result, MemoryOperationOutcome)
        assert recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED) == []

    def test_turn_without_a_tool_call_is_kept_as_a_lapse(self) -> None:
        """LLM が道具を選ばなかった手番は、迷いの行が番号 1 の Lapse として入り、結果を待つ 1 手は無い。写せなかった trace は残らない。"""
        runtime, wiring, recorder = _game(tool_call=None)

        _turn(wiring)

        being_id = runtime._acting_being_for(_ME).being_id
        memory = runtime._being_short_term_memory_store.get(being_id)
        (lapse,) = [e for e in memory.experiences if isinstance(e, Lapse)]
        assert lapse.turn == 1
        assert WORLD_ACTION_HESITATION in lapse.body
        assert memory.awaiting is None
        assert recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED) == []


class TestPromptReadsTheBeingShortTermMemory:
    """本番の手番の流れで、プロンプトの【直近の出来事】と【ここまでのいきさつ】が Being の短期記憶から作られることを保証する (#1824)。"""

    def test_recent_events_section_is_the_being_text_through_observations_memory_operations_and_lapses(self) -> None:
        """預かった観測、待つ 1 手、記憶の道具の 1 手、道具を選ばない手番を重ねると、【直近の出来事】の本文は Being の短期記憶から作った文と同じになる。"""
        runtime, wiring, _ = _game()
        runtime._obs_buffer.append(
            _ME,
            ObservationEntry(
                occurred_at=datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc),
                game_time_label="深夜 0:01",
                output=ObservationOutput(prose="鐘が鳴った", structured={"type": "distant_cue_appeared"}),
            ),
        )
        _turn(wiring)
        wiring.llm_client.set_tool_call_to_return(
            {"name": TOOL_NAME_EPISODE_RECALL, "arguments": {"handles": ["鍵のこと"], "inner_thought": "思い出す"}}
        )
        _turn(wiring)
        wiring.llm_client.set_tool_call_to_return(None)
        _turn(wiring)

        content = _user_content(runtime)

        being_text = recent_events_text(runtime._being_short_term_memory_store.get(_being_id(runtime)))
        assert "鐘が鳴った" in being_text
        assert _recent_events_section(content) == being_text

    def test_recent_events_section_follows_the_being_memory_not_the_current_memory(self) -> None:
        """今の短期記憶に出来事が残っていても、Being の短期記憶を空にすると、【直近の出来事】は「（直近の出来事はありません）」になる。"""
        runtime, wiring, _ = _game()
        _turn(wiring)
        runtime._being_short_term_memory_store.replace_all_by_being(ShortTermMemory.empty(_being_id(runtime)))

        content = _user_content(runtime)

        assert runtime._recent_event_store.get_timeline(_ME) != []
        assert _recent_events_section(content) == NO_RECENT_EVENTS

    def test_backstory_section_shows_the_being_backstories_newest_first(self) -> None:
        """Being の短期記憶にいきさつが 2 つあれば、【ここまでのいきさつ】に新しい順で「[最新]」「[2 世代前]」と出る。"""
        runtime, wiring, _ = _game()
        _turn(wiring)
        being_id = _being_id(runtime)
        runtime._being_short_term_memory_store.replace_all_by_being(
            ShortTermMemory(
                being_id,
                backstories=(
                    Backstory(flow="改札を抜けた", mood="落ち着かない", written_turn=20, until_turn=10),
                    Backstory(flow="ホームで駅員と話した", mood="", written_turn=30, until_turn=20),
                ),
                recent_from=21,
            )
        )

        content = _user_content(runtime)

        assert (
            "【ここまでのいきさつ】\n[最新] ホームで駅員と話した\n\n[2 世代前] 改札を抜けた\n  気分: 落ち着かない"
            in content
        )

    def test_section_breakdown_counts_the_backstory_shown_in_the_prompt(self) -> None:
        """いきさつを出したプロンプトでは、prompt_section_breakdown の backstory_chars が【ここまでのいきさつ】の本文の文字数になる。"""
        runtime, wiring, recorder = _game()
        _turn(wiring)
        being_id = _being_id(runtime)
        backstory = Backstory(flow="改札を抜けた", mood="落ち着かない", written_turn=20, until_turn=10)
        runtime._being_short_term_memory_store.replace_all_by_being(
            ShortTermMemory(being_id, backstories=(backstory,), recent_from=11)
        )

        runtime.build_full_prompt(_ME)

        breakdown = recorder.payloads(TraceEventKind.PROMPT_SECTION_BREAKDOWN)[-1]
        assert breakdown["backstory_chars"] == len("[最新] 改札を抜けた\n  気分: 落ち着かない")

    def test_no_backstory_section_until_a_backstory_arrives(self) -> None:
        """いきさつがまだ無ければ、今の短期記憶の要約があっても【ここまでのいきさつ】は出ない。"""
        runtime, wiring, _ = _game()
        _turn(wiring)

        assert "【ここまでのいきさつ】" not in _user_content(runtime)

    def test_prompt_is_built_after_the_range_fills(self) -> None:
        """Being の短期記憶の範囲が埋まるまで (21 手) 回しても、プロンプトの【直近の出来事】は Being の短期記憶から作った文のまま。"""
        runtime, wiring, recorder = _game()

        for _ in range(RECENT_TURNS + 1):
            _turn(wiring)
            # 本番では turn_trigger が手番の終わりに閉じる。
            runtime._short_term_memory.complete_turn(_ME)
        content = _user_content(runtime)

        assert recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_RANGE_FILLED) != []
        being_text = recent_events_text(runtime._being_short_term_memory_store.get(_being_id(runtime)))
        assert _recent_events_section(content) == being_text


def _being_id(runtime: Any) -> Any:
    return runtime._acting_being_for(_ME).being_id


def _user_content(runtime: Any) -> str:
    return runtime.build_full_prompt(_ME)["messages"][1]["content"]


def _recent_events_section(content: str) -> str:
    """【直近の出来事】の見出しと前置きの 1 行を除いた本文。次の見出しの前で切る。"""
    body = content.split("【直近の出来事】\n", 1)[1].split("\n", 1)[1]
    return body.split("\n\n【", 1)[0]
