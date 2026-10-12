"""環境の tool にだけ予期の引数を付け、書かれた予期をその手のターンの予期として積む配線を保証する (#1441)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    EXPECTATIONS_FIELD_NAME,
)
from ai_rpg_world.application.llm.services.world_llm_turn.phase_a import (
    run_reason_first_phase_a,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_ASSESS_SITUATION,
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.judgment_helpers import ScriptedJudgmentPort
from tests.trace_helpers import RecordingTraceRecorder

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_ME = PlayerId(1)
_SPOT_TOOL_NAMES = frozenset(defn.name for defn, _ in get_spot_graph_specs())

_RAIN = {"what": "雨が降り出す", "when": "今夜", "likelihood": "もしかしたら"}
_REPLY = {"what": "セナが返事をする", "likelihood": "たぶん"}


def _config(*, enabled: bool, **overrides: Any) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.for_tests(
        typed_judgment_provider="stub",
        expectation_settlement_enabled=True,
        prediction_context_id_enabled=True,
        expectation_argument_enabled=enabled,
        **overrides,
    )


def _game(
    *,
    enabled: bool = True,
    overrides: dict[str, Any] | None = None,
    client: ILLMClient | None = None,
    port: ScriptedJudgmentPort | None = None,
) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    runtime = create_world_runtime(
        _DRILL, config=_config(enabled=enabled, **(overrides or {}))
    )
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client
        or StubLlmClient({"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {}}),
        typed_judgment_port=port or ScriptedJudgmentPort(),
    )
    return runtime, wiring, recorder


def _being(runtime: Any) -> BeingId:
    acting = runtime._acting_being_for(_ME)
    assert acting is not None
    return acting.being_id


def _speak(*expectations: Any) -> dict[str, Any]:
    return {
        "name": TOOL_NAME_SPEECH,
        "arguments": {"content": "火はある?", "expectations": list(expectations)},
    }


def _move(wiring: _WorldLlmWiring) -> None:
    result = wiring.run_turn(_ME)
    wiring.llm_turn_trigger._account_result(_ME.value, result)


def _properties(definition: Any) -> dict[str, Any]:
    return definition.parameters.get("properties", {})


def _formed(recorder: RecordingTraceRecorder) -> list[dict[str, Any]]:
    return recorder.payloads(TraceEventKind.EXPECTATION_FORMED)


class TestToolDefinitions:
    """予期の引数が環境の tool にだけ付き、考えるための tool と記憶の tool には付かないことを保証する。"""

    def test_every_environment_tool_has_expectations_and_no_expected_result(
        self,
    ) -> None:
        """有効なとき、送る環境の tool の定義すべてに expectations があり、expected_result はどれにも無い。"""
        runtime, _, _ = _game()

        definitions = runtime.get_tool_definitions(player_id=_ME)

        environment = [d for d in definitions if d.name in _SPOT_TOOL_NAMES]
        assert environment
        assert all(EXPECTATIONS_FIELD_NAME in _properties(d) for d in environment)
        assert all("expected_result" not in _properties(d) for d in definitions)

    def test_memory_tools_do_not_get_expectations(self) -> None:
        """有効なときも、todo や memo のような記憶の tool には expectations を付けない。"""
        runtime, _, _ = _game()

        definitions = runtime.get_tool_definitions(player_id=_ME)

        others = [d for d in definitions if d.name not in _SPOT_TOOL_NAMES]
        assert others
        assert all(EXPECTATIONS_FIELD_NAME not in _properties(d) for d in others)

    def test_disabled_leaves_tool_definitions_unchanged(self) -> None:
        """無効なとき、送る環境の tool の定義は tool catalog の元の定義と同じで、どの tool にも expectations は無い。"""
        runtime, _, _ = _game(enabled=False)
        catalog = {defn.name: defn.parameters for defn, _ in get_spot_graph_specs()}

        definitions = runtime.get_tool_definitions(player_id=_ME)

        environment = [d for d in definitions if d.name in catalog]
        assert environment
        assert all(d.parameters == catalog[d.name] for d in environment)
        assert all(EXPECTATIONS_FIELD_NAME not in _properties(d) for d in definitions)

    def test_definitions_do_not_change_across_turns(self) -> None:
        """手を打ってターン数が進んでも、送る tool の定義はバイト単位で変わらない。"""
        runtime, wiring, _ = _game()
        before = json.dumps(
            [d.parameters for d in runtime.get_tool_definitions(player_id=_ME)],
            ensure_ascii=False,
        )

        _move(wiring)
        _move(wiring)

        assert runtime._memory_turn_clock.current_turn(_being(runtime)) == 2
        after = json.dumps(
            [d.parameters for d in runtime.get_tool_definitions(player_id=_ME)],
            ensure_ascii=False,
        )
        assert before == after

    def test_reason_first_assessment_has_neither_argument(self) -> None:
        """2 段階ターンの 1 段目の assess_situation には expectations も expected_result も無く、2 段目の行動の tool には expectations がある。"""
        runtime, _, _ = _game()

        definitions = runtime.get_tool_definitions(
            player_id=_ME, tool_schema_mode="reason_first"
        )

        (assess,) = [d for d in definitions if d.name == TOOL_NAME_ASSESS_SITUATION]
        assert EXPECTATIONS_FIELD_NAME not in _properties(assess)
        assert "expected_result" not in _properties(assess)
        environment = [d for d in definitions if d.name in _SPOT_TOOL_NAMES]
        assert all(EXPECTATIONS_FIELD_NAME in _properties(d) for d in environment)


class TestActionRules:
    """行動ルールに、予期の書き方の 1 行が有効なときだけ入ることを保証する。"""

    def test_enabled_rules_ask_for_expectations(self) -> None:
        """有効なとき、system prompt の行動ルールに expectations の書き方の行があり、expected_result の行は無い。"""
        runtime, _, _ = _game()

        system = runtime.build_full_prompt(_ME)["messages"][0]["content"]

        assert f"`{EXPECTATIONS_FIELD_NAME}`" in system
        assert "expected_result" not in system

    def test_disabled_rules_are_unchanged(self) -> None:
        """無効なときの system prompt は、有効なときの prompt から予期の書き方の 1 行だけを除いたものとバイト単位で一致する。"""
        enabled, _, _ = _game()
        disabled, _, _ = _game(enabled=False)
        enabled_system = enabled.build_full_prompt(_ME)["messages"][0]["content"]
        (rule,) = [
            line
            for line in enabled_system.splitlines()
            if f"`{EXPECTATIONS_FIELD_NAME}`" in line
        ]

        system = disabled.build_full_prompt(_ME)["messages"][0]["content"]

        assert system == enabled_system.replace("\n" + rule, "", 1)
        assert EXPECTATIONS_FIELD_NAME not in system


class TestFormingFromACall:
    """tool 呼び出しに書かれた予期を、その手のターンの予期として積み、trace に残すことを保証する。"""

    def test_expectations_written_on_speech_are_formed_at_that_turn(self) -> None:
        """発言に書かれた 2 件の予期は、その手で進んだターン数を持つ清算待ちの予期として積まれる。"""
        runtime, wiring, _ = _game(client=StubLlmClient(_speak(_REPLY, _RAIN)))
        being = _being(runtime)

        _move(wiring)

        formed = runtime._expectation_store.list_all_by_being(being)
        assert [(e.content, e.due, e.likelihood, e.formed_at_turn) for e in formed] == [
            ("セナが返事をする", None, Likelihood.PROBABLY, 1),
            ("雨が降り出す", "今夜", Likelihood.MAYBE, 1),
        ]

    def test_formed_expectations_are_asked_their_shape_at_the_end_of_the_turn(
        self,
    ) -> None:
        """積んだ予期は、同じターンの終わりの清算で形の問いを受ける。"""
        port = ScriptedJudgmentPort()
        _, wiring, _ = _game(client=StubLlmClient(_speak(_REPLY)), port=port)

        _move(wiring)

        _, questions = port.calls[-1]
        assert set(questions) == {"shape_0", "scene_changed"}

    def test_what_was_in_mind_comes_from_the_prompt_of_that_turn(self) -> None:
        """頭にあった信念と想起は、そのターンのプロンプトを組んだときに載った信念と想起したエピソードから取る。"""
        runtime, wiring, _ = _game(client=StubLlmClient(_speak(_REPLY)))
        being = _being(runtime)
        phase_a = wiring.run_phase_a(_ME)
        ledger = runtime._get_prediction_context_ledger()
        context = ledger.peek(_ME)
        ledger.attach(
            _ME,
            context.prediction_context_id,
            episode_ids=("episode-7",),
            belief_ids=("belief-1", "belief-2"),
        )

        wiring.run_phase_b(phase_a)

        (formed,) = runtime._expectation_store.list_all_by_being(being)
        assert formed.beliefs_in_mind == ("belief-1", "belief-2")
        assert formed.episodes_in_mind == ("episode-7",)

    def test_formed_expectations_are_traced_with_their_content(self) -> None:
        """積んだ予期の件数と中身を、行動ごとの trace に残す。"""
        runtime, wiring, recorder = _game(client=StubLlmClient(_speak(_REPLY)))
        being = _being(runtime)

        _move(wiring)

        (trace,) = _formed(recorder)
        assert trace["being_id"] == being.value
        assert trace["tool"] == TOOL_NAME_SPEECH
        assert trace["turn"] == 1
        assert trace["formed_count"] == 1
        assert trace["formed"] == [
            {
                "expectation_id": f"{being.value}:t1:0",
                "what": "セナが返事をする",
                "when": None,
                "likelihood": "probably",
            }
        ]
        assert trace["rejected"] == []
        assert trace["context_found"] is True

    def test_empty_expectations_form_nothing(self) -> None:
        """予期が空の呼び出しは何も積まず、trace には 0 件として残す。"""
        runtime, wiring, recorder = _game(client=StubLlmClient(_speak()))

        _move(wiring)

        assert runtime._expectation_store.list_all_by_being(_being(runtime)) == []
        (trace,) = _formed(recorder)
        assert (trace["formed_count"], trace["argument_present"]) == (0, True)

    def test_unknown_likelihood_is_not_formed_and_the_reason_is_traced(self) -> None:
        """確からしさが決まった値以外の予期は積まず、外した理由と元の値を trace に残す。"""
        bad = {"what": "雨が降る", "likelihood": "probably"}
        runtime, wiring, recorder = _game(client=StubLlmClient(_speak(bad, _REPLY)))

        _move(wiring)

        formed = runtime._expectation_store.list_all_by_being(_being(runtime))
        assert [e.content for e in formed] == ["セナが返事をする"]
        (trace,) = _formed(recorder)
        assert trace["rejected"] == [
            {"index": 0, "reason": "invalid_likelihood", "raw": bad}
        ]

    def test_expectations_on_other_environment_tools_are_formed_too(self) -> None:
        """発言のほかの環境の tool (待機) に書かれた予期も、同じ規則で積まれる。"""
        wait = {
            "name": TOOL_NAME_SPOT_GRAPH_WAIT,
            "arguments": {"expectations": [_RAIN]},
        }
        runtime, wiring, _ = _game(client=StubLlmClient(wait))

        _move(wiring)

        formed = runtime._expectation_store.list_all_by_being(_being(runtime))
        assert [e.content for e in formed] == ["雨が降り出す"]

    def test_expectations_on_a_failed_action_are_still_formed(self) -> None:
        """行動が失敗しても、その行動に書かれた予期は積まれる。"""
        travel = {
            "name": TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            "arguments": {
                "destination_label": "どこにも無い場所",
                "expectations": [_REPLY],
            },
        }
        runtime, wiring, _ = _game(client=StubLlmClient(travel))

        result = wiring.run_turn(_ME)

        assert result.success is False
        formed = runtime._expectation_store.list_all_by_being(_being(runtime))
        assert [e.content for e in formed] == ["セナが返事をする"]

    def test_terms_from_the_profile_set_the_expiry(self) -> None:
        """profile が書いた期限のターン数が、積んだ予期の期限になる。"""
        runtime, wiring, _ = _game(
            client=StubLlmClient(_speak(_REPLY, _RAIN)),
            overrides={
                "expectation_undated_term_turns": 3,
                "expectation_dated_term_turns": 12,
            },
        )

        _move(wiring)

        formed = runtime._expectation_store.list_all_by_being(_being(runtime))
        assert [e.expires_at_turn for e in formed] == [1 + 3, 1 + 12]

    def test_forming_failure_does_not_stop_the_turn_and_is_traced(self) -> None:
        """予期を積む途中で失敗しても行動は実行され、失敗の理由を trace に残す。"""
        runtime, wiring, recorder = _game(client=StubLlmClient(_speak(_REPLY)))
        forming = wiring.expectation_forming
        assert forming is not None

        def broken(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("store is down")

        forming.form = broken  # type: ignore[method-assign]

        wiring.run_turn(_ME)

        assert [p["tool"] for p in recorder.payloads(TraceEventKind.ACTION_RESULT)] == [
            TOOL_NAME_SPEECH
        ]
        (trace,) = _formed(recorder)
        assert trace["skipped_reason"] == "forming_failed"
        assert trace["error"] == "RuntimeError: store is down"
        assert trace["formed_count"] == 0

    def test_missing_prompt_context_is_traced(self) -> None:
        """そのターンのプロンプトの信念と想起を台帳から引けなかったときは、0 件だったのと区別できるよう trace に残す。"""
        runtime, wiring, recorder = _game(client=StubLlmClient(_speak(_REPLY)))
        phase_a = wiring.run_phase_a(_ME)
        runtime._get_prediction_context_ledger().consume(_ME)

        wiring.run_phase_b(phase_a)

        (trace,) = _formed(recorder)
        assert trace["context_found"] is False
        assert trace["formed_count"] == 1

    def test_expectations_slipped_into_a_memory_tool_are_not_formed(self) -> None:
        """予期の引数を付けていない記憶の tool の呼び出しに予期が紛れていても、積まず trace も出さない。"""
        memo = {
            "name": TOOL_NAME_MEMO_ADD,
            "arguments": {"content": "火を探す", "expectations": [_REPLY]},
        }
        runtime, wiring, recorder = _game(client=StubLlmClient(memo))

        _move(wiring)

        assert runtime._expectation_store.list_all_by_being(_being(runtime)) == []
        assert _formed(recorder) == []

    def test_disabled_forms_nothing_even_if_written(self) -> None:
        """無効なとき、呼び出しに予期が書かれていても積まず、trace も出さない。"""
        runtime, wiring, recorder = _game(
            enabled=False, client=StubLlmClient(_speak(_REPLY))
        )

        _move(wiring)

        assert runtime._expectation_store.list_all_by_being(_being(runtime)) == []
        assert _formed(recorder) == []


class _SequencedClient(StubLlmClient):
    def __init__(self, *tool_calls: dict[str, Any]) -> None:
        super().__init__(None)
        self._queue = list(tool_calls)

    def invoke(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        self.set_tool_call_to_return(self._queue.pop(0))
        return super().invoke(*args, **kwargs)


class TestReasonFirstTurn:
    """2 段階ターンでは、2 段目の行動に書かれた予期だけが積まれることを保証する。"""

    def test_action_phase_expectations_are_formed_and_assessment_is_not(self) -> None:
        """1 段目の評価の文は予期として積まれず、2 段目の行動の tool に書かれた予期だけが積まれる。"""
        assess = {
            "name": TOOL_NAME_ASSESS_SITUATION,
            "arguments": {
                "inner_thought": "セナはきっと答えてくれる",
                "expectations": [{"what": "評価に書いた予期", "likelihood": "たぶん"}],
            },
        }
        client = _SequencedClient(assess, _speak(_REPLY))
        runtime, wiring, _ = _game(client=client)
        prompt = runtime.build_full_prompt(_ME)

        phase_a = run_reason_first_phase_a(wiring, _ME, prompt, gate_reason="test")
        wiring.run_phase_b(phase_a)

        formed = runtime._expectation_store.list_all_by_being(_being(runtime))
        assert [e.content for e in formed] == ["セナが返事をする"]
