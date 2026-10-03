"""状況の欄から引く run で、ターンの終わりの清算が選んだ欄が、次の手のプロンプトの想起に使われる配線を保証する (#1414)。

LLM と Jev は呼ばない。判断ポートは台本で答える。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_rpg_world.application.being.recall.body_band import BODY_BAND_QUESTION
from ai_rpg_world.application.being.recall.situation import (
    RECALL_FIELDS_QUESTION,
    SELECTABLE_FIELDS,
    SituationField,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_WAIT
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.application.being.expectation.support import (
    FieldRankingPort,
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)
from tests.runtime_config_helpers import episodic_config

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_ME = PlayerId(1)


def _game(
    port: ScriptedJudgmentPort,
    *,
    settlement: bool = True,
    recall: bool = True,
    keep: int = 2,
) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    config = episodic_config(
        semantic_passive_top_k=3,
        situation_fields_to_keep=keep,
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
        port = FieldRankingPort(
            rankings=[(SituationField.HAPPENING, SituationField.INTENT)]
        )
        _, wiring, recorder = _game(port)

        _move(wiring)
        _move(wiring)

        first, second = _recalls(recorder)[:2]
        assert first["degraded_reason"] == "no_selection"
        assert len(first["kept_fields"]) == len(SELECTABLE_FIELDS)
        assert second["degraded_reason"] is None
        assert second["kept_fields"] == ["やろうとしていること", "いま起きたこと"]

    def test_profile_sets_how_many_fields_the_next_prompt_keeps(self) -> None:
        """profile の残す欄の数が清算に届き、次の手のプロンプトはその数の欄で引く。"""
        port = FieldRankingPort(rankings=[(SituationField.HAPPENING, SituationField.INTENT)])
        _, wiring, recorder = _game(port, keep=1)

        _move(wiring)
        _move(wiring)

        assert _recalls(recorder)[1]["kept_fields"] == ["いま起きたこと"]

    def test_settlement_asks_fields_even_without_expectations(self) -> None:
        """予期が 1 件も無い手でも、ターンの終わりに Jev を呼んで欄を問う。"""
        port = ScriptedJudgmentPort()
        _, wiring, _ = _game(port)

        _move(wiring)

        assert len(port.calls) == 1
        assert set(port.calls[0][1]) == {RECALL_FIELDS_QUESTION, BODY_BAND_QUESTION}

    def test_settlement_shows_the_situation_at_the_end_of_the_turn(self) -> None:
        """ターンの終わりの清算は、その手の結果を含むいまの状況の欄の値を Jev の state と清算の trace に載せる。"""
        port = ScriptedJudgmentPort()
        _, wiring, recorder = _game(port)

        _move(wiring)

        shown = port.calls[0][0]["いまの状況"]
        assert set(shown) == {f.value for f in SituationField}
        assert shown["いま起きたこと"], "その手の結果がいま起きたことに入る"
        settlement = recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[-1]
        assert settlement["state"]["いまの状況"] == shown
        assert settlement["field_selection"]["situation_shown"] is True

    def test_situation_at_turn_end_leaves_out_the_body_band(self) -> None:
        """ターンの終わりに組む状況には、前のターンに読んだ体の帯の文を入れない。帯はこの清算で決めるため。"""
        from ai_rpg_world.application.being.recall.body_band import BodyBand, BodyBandReading
        from ai_rpg_world.application.being.recall.situation import FieldSelection

        runtime, wiring, _ = _game(ScriptedJudgmentPort())
        _move(wiring)
        being = runtime._acting_being_for(_ME).being_id
        runtime._next_turn_field_selections.put(
            being,
            settled_turn=runtime._expectation_store.current_turn(being),
            selection=FieldSelection(kept=frozenset()),
            band=BodyBandReading(BodyBand.CRISIS),
        )

        situation, skipped = runtime.situation_at_turn_end(_ME, being)

        assert not any("体の状態は" in text for text in situation.own_state)
        assert isinstance(skipped, dict)

    def test_situation_is_not_built_when_fields_are_not_asked(self, monkeypatch: Any) -> None:
        """状況の欄から引かない run では、ターンの終わりに状況を組まない。"""
        runtime, wiring, _ = _game(ScriptedJudgmentPort(), recall=False)
        calls: list[Any] = []
        monkeypatch.setattr(runtime, "situation_at_turn_end", lambda *a: calls.append(a))

        _move(wiring)

        assert calls == []

    def test_settlement_still_asks_when_the_situation_cannot_be_built(self, monkeypatch: Any) -> None:
        """ターンの終わりの状況を組めなくても清算は止めず、欄の値を見せずに問う。"""
        port = ScriptedJudgmentPort()
        runtime, wiring, recorder = _game(port)

        def _broken(*_args: Any) -> Any:
            raise RuntimeError("broken")

        monkeypatch.setattr(runtime, "situation_at_turn_end", _broken)

        _move(wiring)

        assert len(port.calls) == 1
        assert "いまの状況" not in port.calls[0][0]
        settlement = recorder.payloads(TraceEventKind.EXPECTATION_SETTLEMENT)[-1]
        assert "いまの状況" not in settlement["state"]
        assert settlement["field_selection"]["situation_shown"] is False
        assert "RuntimeError" in settlement["field_selection"]["situation_note"]["unavailable"]

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
