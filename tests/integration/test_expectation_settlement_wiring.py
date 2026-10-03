"""ゲームの runtime が予期の store を持ち、1 手ごとに Being のターン数を進め、ターンの終わりに予期を清算する配線を保証する (#1440)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.being.expectation.grounds import (
    MemoryStoreInMindTextReader,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)
from tests.runtime_config_helpers import episodic_config

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_ME = PlayerId(1)


def _game(
    *, enabled: bool = True, port: ScriptedJudgmentPort | None = None
) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    config = ResolvedLlmRuntimeConfig.for_tests(
        typed_judgment_provider="stub",
        expectation_settlement_enabled=enabled,
    )
    runtime = create_world_runtime(_DRILL, config=config)
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient({"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {}}),
        typed_judgment_port=port or ScriptedJudgmentPort(),
    )
    return runtime, wiring, recorder


def _being(runtime: Any) -> BeingId:
    acting = runtime._acting_being_for(_ME)
    assert acting is not None
    return acting.being_id


def _move(wiring: _WorldLlmWiring) -> None:
    result = wiring.run_turn(_ME)
    wiring.llm_turn_trigger._account_result(_ME.value, result)


def _expectation(being: BeingId, turn: int, content: str) -> Expectation:
    return Expectation(
        expectation_id=ExpectationId(f"exp-{turn}"),
        holder=being,
        content=content,
        origin=ExpectationOrigin.WITH_ACTION,
        likelihood=Likelihood.PROBABLY,
        formed_at_turn=turn,
        expires_at_turn=turn + 10,
    )


def _settlements(recorder: RecordingTraceRecorder) -> list[dict[str, Any]]:
    return recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)


class TestMemoryTurn:
    """エージェントが 1 手を打つたびに Being のターン数が 1 進み、予期を作るターンと清算のターンがそろう挙動を保証する。"""

    def test_each_move_advances_the_being_turn_by_one(self) -> None:
        """エージェントが 2 手打つと、予期の store にある Being のターン数は 0 から 2 になる。"""
        runtime, wiring, _ = _game(enabled=False)
        being = _being(runtime)
        before = runtime._expectation_store.current_turn(being)

        _move(wiring)
        _move(wiring)

        assert (before, runtime._expectation_store.current_turn(being)) == (0, 2)

    def test_expectation_formed_during_a_move_gets_that_turn_and_shape_is_asked(
        self,
    ) -> None:
        """手を打っている最中に作った予期は、その手で進んだターン数を持ち、同じターンの終わりに形の問いだけを受ける。予期を積む入口 (#1441) はまだ無いので、試験が手の途中のターン数を読んで予期を作り、ターン数を手の入口で進める順序を守る。"""
        port = ScriptedJudgmentPort()
        runtime, wiring, recorder = _game(port=port)
        being = _being(runtime)
        store = runtime._expectation_store
        _move(wiring)

        phase_a = wiring.run_phase_a(_ME)
        result = wiring.run_phase_b(phase_a)
        turn = store.current_turn(being)
        store.save(_expectation(being, turn, "カイが焚き火を起こす"), [])
        wiring.llm_turn_trigger._account_result(_ME.value, result)

        assert turn == 2
        _, questions = port.calls[-1]
        assert set(questions) == {"shape_0", "scene_changed"}
        assert _settlements(recorder)[-1]["turn"] == 2


class TestTurnMaterial:
    """清算の時系列に、前の自分のターンからこのターンまでに届いた出来事が、行動と発言に分けて載る挙動を保証する。"""

    def test_other_speech_and_own_action_are_split(self) -> None:
        """他の人の発言は「発言」に、自分の行動の結果は「行動」に入り、どちらも本人の名前で書かれる。"""
        port = ScriptedJudgmentPort({"check_0": "undetermined"})
        runtime, wiring, _ = _game(port=port)
        being = _being(runtime)
        store = runtime._expectation_store
        store.advance_turn(being)
        store.save(_expectation(being, 1, "カイが焚き火を起こす"), [])
        runtime._obs_buffer.append(
            _ME,
            ObservationEntry(
                occurred_at=datetime.now(timezone.utc),
                output=ObservationOutput(
                    prose="カイが「火打ち石はある」と言った。",
                    structured={"type": "player_spoke", "speaker": "カイ"},
                    observation_category="social",
                ),
                game_time_label="朝 8:00",
            ),
        )

        _move(wiring)

        state, _ = port.calls[-1]
        (latest,) = [t for t in state["出来事の時系列"] if t["ターン"] == "ターン2"]
        assert latest["発言"] == ["[朝 8:00] カイが「火打ち石はある」と言った。"]
        (own,) = latest["行動"]
        assert f"] {runtime.get_player_name(_ME)}: その場で待機した" in own
        assert state["本人の名前"] == runtime.get_player_name(_ME)

    def test_own_speech_goes_to_speeches(self) -> None:
        """自分の発言の行動は「行動」ではなく「発言」に入る。"""
        port = ScriptedJudgmentPort({"check_0": "undetermined"})
        runtime, wiring, _ = _game(port=port)
        being = _being(runtime)
        store = runtime._expectation_store
        store.advance_turn(being)
        store.save(_expectation(being, 1, "カイが返事をする"), [])
        wiring.llm_client = StubLlmClient(
            {"name": TOOL_NAME_SPEECH, "arguments": {"content": "火はある?"}}
        )

        _move(wiring)

        state, _ = port.calls[-1]
        (latest,) = [t for t in state["出来事の時系列"] if t["ターン"] == "ターン2"]
        assert latest["行動"] == []
        assert len(latest["発言"]) == 1


class TestSettlementWiring:
    """清算の有効化と、store・配り手が runtime から拾える配線を保証する。"""

    def test_disabled_settlement_never_calls_the_port(self) -> None:
        """清算を有効にしない run では、清算待ちの予期があっても Jev を呼ばず、清算の trace も出ない。"""
        port = ScriptedJudgmentPort()
        runtime, wiring, recorder = _game(enabled=False, port=port)
        being = _being(runtime)
        runtime._expectation_store.save(_expectation(being, 0, "カイが来る"), [])

        _move(wiring)

        assert port.calls == []
        assert _settlements(recorder) == []

    def test_enabled_settlement_without_a_port_fails_at_wiring(self) -> None:
        """清算を有効にしたのに判断ポートが無い wiring は、組むときに ValueError で落ちる。"""
        config = ResolvedLlmRuntimeConfig.for_tests(
            typed_judgment_provider="stub", expectation_settlement_enabled=True
        )
        runtime = create_world_runtime(_DRILL, config=config)

        with pytest.raises(ValueError, match="EXPECTATION_SETTLEMENT_ENABLED"):
            _WorldLlmWiring(
                runtime=runtime,
                observation_buffer=runtime._obs_buffer,
                short_term_memory=runtime._short_term_memory,
                llm_client=StubLlmClient(None),
            )

    def test_settling_twice_in_one_turn_is_traced_as_failure(self) -> None:
        """ターン数を進めずに同じターンをもう一度閉じると、ゲームのターンは止めずに、清算の失敗を理由とともに trace に残す。"""
        runtime, wiring, recorder = _game()
        result = wiring.run_turn(_ME)
        wiring.llm_turn_trigger._account_result(_ME.value, result)

        wiring.llm_turn_trigger._account_result(_ME.value, result)

        failed = _settlements(recorder)[-1]
        assert failed["skipped_reason"] == "settlement_failed"
        assert failed["unavailable_reason"].startswith("ValueError: turn 1")

    def test_profile_limits_reach_the_settlement_and_the_dispatcher(self) -> None:
        """profile に書いた清算待ちの上限・時系列のターン数・配り直しの上限が、組まれた清算の service と配り手に届く。"""
        config = ResolvedLlmRuntimeConfig.for_tests(
            typed_judgment_provider="stub",
            expectation_settlement_enabled=True,
            expectation_settlement_max_open=5,
            expectation_settlement_timeline_turns=2,
            expectation_event_max_delivery_attempts=7,
        )
        runtime = create_world_runtime(_DRILL, config=config)

        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=StubLlmClient(None),
            typed_judgment_port=ScriptedJudgmentPort(),
        )

        settlement = wiring.expectation_settlement
        assert settlement is not None
        assert (settlement._max_open, settlement._timeline_turns) == (5, 2)
        assert runtime._expectation_dispatcher._max_attempts == 7

    def test_profile_grounds_settings_reach_the_settlement(self) -> None:
        """profile に書いた根拠の問いの上限と確率の閾値が、組まれた清算の service に届く。"""
        config = ResolvedLlmRuntimeConfig.for_tests(
            typed_judgment_provider="stub",
            expectation_settlement_enabled=True,
            expectation_grounds_max_questions=3,
            expectation_grounds_min_probability=0.7,
        )
        runtime = create_world_runtime(_DRILL, config=config)

        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=StubLlmClient(None),
            typed_judgment_port=ScriptedJudgmentPort(),
        )

        settlement = wiring.expectation_settlement
        assert settlement is not None
        assert (settlement._max_grounds_questions, settlement._grounds_min_probability) == (
            3,
            0.7,
        )

    def test_grounds_reader_reads_the_episodic_stack_stores(self) -> None:
        """根拠の本文を引く口は、プロンプトの想起と同じ episodic stack の信念・エピソード・再解釈の store を読む。"""
        config = episodic_config(
            typed_judgment_provider="stub", expectation_settlement_enabled=True
        )
        runtime = create_world_runtime(_DRILL, config=config)
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=StubLlmClient(None),
            typed_judgment_port=ScriptedJudgmentPort(),
        )

        settlement = wiring.expectation_settlement
        assert settlement is not None
        reader = settlement._grounds_reader
        assert isinstance(reader, MemoryStoreInMindTextReader)
        stack = runtime._episodic_stack
        assert reader._semantic_store is stack.semantic_memory_store
        assert reader._episode_store is stack.episode_store
        assert reader._journal_store is stack.reinterpretation_journal

    def test_settlement_dispatcher_and_turn_share_one_store(self) -> None:
        """清算・配り手・1 手ごとのターン数・snapshot が拾う store は、runtime の予期の store 1 つを指す。手を打つと、その 1 つのターン数だけが進む。"""
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        runtime, wiring, _ = _game()
        store = runtime._expectation_store
        settlement = wiring.expectation_settlement
        assert settlement is not None

        _move(wiring)

        assert settlement._repository is store
        assert runtime._expectation_dispatcher._repository is store
        assert _wiring_stub_from_world_runtime(runtime).expectation_store is store
        assert store.current_turn(_being(runtime)) == 1

    def test_snapshot_stub_picks_up_the_runtime_store(self) -> None:
        """実験の snapshot が拾う配線は runtime の予期の store そのものを指し、空の代用品に落ちない (store_wired が真になる)。"""
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        runtime, _, _ = _game(enabled=False)

        stub = _wiring_stub_from_world_runtime(runtime)

        assert stub.expectation_store is runtime._expectation_store

    def test_resume_redelivers_restored_undelivered_events(self) -> None:
        """再開した直後に配り直しを呼ぶと、snapshot から戻った未配信の出来事が配られ、受け取る側がまだ無いことを示す記録が trace に残る。"""
        runtime, _, recorder = _game(enabled=False)
        being = _being(runtime)
        expectation = _expectation(being, 1, "カイが来る")
        expectation.record(Check(turn=2, verdict=CheckVerdict.HIT))
        settled = expectation.record(Check(turn=3, verdict=CheckVerdict.HIT))
        assert settled is not None
        from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
            UndeliveredExpectationEvent,
        )

        runtime._expectation_store.replace_all_by_being(
            being,
            expectations=[expectation],
            undelivered_events=[UndeliveredExpectationEvent.of(settled)],
            turn=3,
        )

        runtime.redeliver_expectation_events([being])

        assert runtime._expectation_store.list_undelivered_by_being(being) == []
        (delivery,) = recorder.payloads(TraceEventKind.EXPECTATION_EVENT_DELIVERY)
        assert (delivery["event_id"], delivery["outcome"]) == ("exp-1@3", "no_receivers")
