"""状況の欄から引く run で、ターンの終わりの清算が選んだ欄が、次の手のプロンプトの想起に使われる配線を保証する (#1414)。

LLM と Jev は呼ばない。判断ポートは台本で答える。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_rpg_world.application.being.recall.body_band import BODY_BAND_QUESTION
from ai_rpg_world.application.being.recall.situation import (
    DROP,
    KEEP,
    SELECTABLE_FIELDS,
    SituationField,
    field_question_name,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_WAIT
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)
from tests.runtime_config_helpers import episodic_config

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_ME = PlayerId(1)


def _fields(keep: set[SituationField]) -> dict[str, str]:
    return {field_question_name(f): KEEP if f in keep else DROP for f in SELECTABLE_FIELDS}


def _game(
    port: ScriptedJudgmentPort, *, settlement: bool = True, recall: bool = True
) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    config = episodic_config(
        semantic_passive_top_k=3,
        situation_belief_recall_enabled=recall,
        typed_judgment_provider="stub",
        expectation_settlement_enabled=settlement,
    )
    runtime = create_world_runtime(_DRILL, config=config)
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient({"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {}}),
        typed_judgment_port=port,
    )
    return runtime, wiring, recorder


def _move(wiring: _WorldLlmWiring) -> None:
    result = wiring.run_turn(_ME)
    wiring.llm_turn_trigger._account_result(_ME.value, result)


def _recalls(recorder: RecordingTraceRecorder) -> list[dict[str, Any]]:
    return recorder.payloads(TraceEventKind.SITUATION_BELIEF_RECALL)


class TestSelectionFlowsFromSettlementToTheNextPrompt:
    """清算で選んだ欄が、次の手のプロンプトの想起に届くことを保証する。"""

    def test_first_prompt_has_no_selection_and_the_next_uses_the_settled_one(self) -> None:
        """最初の手のプロンプトは選択が無いので全部の欄で引き、その手の清算で選んだ欄が次の手のプロンプトで使われる。"""
        port = ScriptedJudgmentPort(_fields({SituationField.HAPPENING}))
        _, wiring, recorder = _game(port)

        _move(wiring)
        _move(wiring)

        first, second = _recalls(recorder)[:2]
        assert first["degraded_reason"] == "no_selection"
        assert len(first["kept_fields"]) == len(SELECTABLE_FIELDS)
        assert second["degraded_reason"] is None
        assert second["kept_fields"] == ["いま起きたこと"]

    def test_settlement_asks_fields_even_without_expectations(self) -> None:
        """予期が 1 件も無い手でも、ターンの終わりに Jev を呼んで欄を問う。"""
        port = ScriptedJudgmentPort()
        _, wiring, _ = _game(port)

        _move(wiring)

        assert len(port.calls) == 1
        assert set(port.calls[0][1]) == {
            field_question_name(f) for f in SELECTABLE_FIELDS
        } | {BODY_BAND_QUESTION}

    def test_without_settlement_the_prompt_says_settlement_is_disabled(self) -> None:
        """清算を切った run では欄が選ばれず、清算が無いことを縮退の理由に持って全部の欄で引く。最初のターンの no_selection とは分けて数えられる。"""
        _, wiring, recorder = _game(ScriptedJudgmentPort(), settlement=False)

        _move(wiring)
        _move(wiring)

        recalls = _recalls(recorder)
        assert {r["degraded_reason"] for r in recalls} == {"settlement_disabled"}
        assert all(len(r["kept_fields"]) == len(SELECTABLE_FIELDS) for r in recalls)
        assert all("settlement is disabled" in r["degraded_detail"] for r in recalls)

    def test_settlement_without_situation_recall_does_not_ask_fields(self) -> None:
        """状況の欄から引かない run の清算は欄を問わず、予期の無いターンに Jev を呼ばない (いままでどおり)。"""
        port = ScriptedJudgmentPort()
        _, wiring, recorder = _game(port, recall=False)

        _move(wiring)

        assert port.calls == []
        settlements = recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)
        assert [s["field_selection"] for s in settlements] == [None]
