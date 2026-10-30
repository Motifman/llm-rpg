"""対象の名前を意味で選び直したとき、判断が trace に残り、解釈が結果文で当人に届く。

黙って置き換えない。黙って通すと、書いた名前で通ったと学んで同じ名前を書き続ける。
採らなかった判断も残す。残さないと「問わなかった」と「問って断った」が同じに見える。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_label_rescue import (
    NO_MATCH_OPTION,
    TargetLabelRescue,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    adapt_executor_handler_with_resolver,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_INTERACT
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _FixedPort(ITypedJudgmentPort):
    def __init__(self, chosen: str = "東の祭壇", probability: float = 0.95) -> None:
        self._chosen, self._probability = chosen, probability

    def judge(self, state: str | Mapping[str, Any] | Sequence[Any], questions: Mapping[str, Question]):
        name = next(iter(questions))
        return {
            name: JudgmentResult(
                value=self._chosen,
                probabilities={self._chosen: self._probability},
                confidence=0.92,
                source=JudgmentSource.JEV,
                latency_ms=120.0,
            )
        }


class _RecordingTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        self.events.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["kind"] == kind]


def _context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "O1": ToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="東の祭壇",
                world_object_id=11,
                available_interactions=("offer",),
                interaction_labels=(("offer", "供物を捧げる"),),
            ),
            "O2": ToolRuntimeTargetDto(
                label="O2",
                kind="spot_graph_object",
                display_name="西の祭壇",
                world_object_id=12,
                available_interactions=("offer",),
                interaction_labels=(("offer", "供物を捧げる"),),
            ),
        }
    )


def _call(written: str, *, port: ITypedJudgmentPort | None, trace: _RecordingTrace | None = None):
    seen: list[dict[str, Any]] = []

    def raw_handler(_pid: int, resolved: dict[str, Any], _ctx: Any) -> LlmCommandResultDto:
        seen.append(resolved)
        return LlmCommandResultDto(success=True, message="供物を捧げた")

    rescue = TargetLabelRescue(port=port, min_confidence=0.85) if port is not None else None
    handler = adapt_executor_handler_with_resolver(
        raw_handler,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        SpotGraphArgumentResolver(target_label_rescue=rescue),
        trace_recorder_provider=(lambda: trace) if trace is not None else None,
        current_tick_provider=(lambda: 7) if trace is not None else None,
    )
    result = handler(
        PlayerId(3), {"target_label": written, "action_name": "offer", "inner_thought": "祭壇に捧げる"}, _context()
    )
    return result, seen


class TestTheAgentIsToldHowItsTargetWasRead:
    def test_a_replaced_target_is_explained_and_the_executor_gets_the_real_object(self) -> None:
        """置き換えた対象は結果文の先頭で説明され、executor には解決した object_id が届く。"""
        result, seen = _call("East Shrine", port=_FixedPort())

        assert result.success is True
        assert result.message.startswith("「East Shrine」は「東の祭壇」と解釈した。")
        assert "供物を捧げた" in result.message
        assert seen[0]["object_id"] == 11

    def test_a_matching_target_gets_no_note(self) -> None:
        """候補に当たった名前は問われず、結果文に注釈も付かない (**正の対照**)。"""
        result, _ = _call("東の祭壇", port=_FixedPort())

        assert result.message == "供物を捧げた"


class TestTheJudgmentIsTraced:
    def test_an_accepted_judgment_is_traced(self) -> None:
        """採用した判断は question=target_label_rescue で、元の値・選択・確率・閾値・採否つきで残る。"""
        trace = _RecordingTrace()
        _call("East Shrine", port=_FixedPort(), trace=trace)

        events = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)
        assert len(events) == 1
        e = events[0]
        assert e["question"] == "target_label_rescue"
        assert e["original"] == "East Shrine" and e["replaced_with"] == "東の祭壇"
        assert e["probability"] == 0.95 and e["min_confidence"] == 0.85 and e["accepted"] is True
        assert e["player_id"] == 3 and e["tick"] == 7

    def test_a_no_match_answer_keeps_the_failure_and_is_traced(self) -> None:
        """「該当なし」なら従来どおり INVALID_TARGET_LABEL で失敗し、断った判断も trace に残る。"""
        trace = _RecordingTrace()
        result, seen = _call("大型カニ", port=_FixedPort(chosen=NO_MATCH_OPTION), trace=trace)

        assert result.success is False and result.error_code == "INVALID_TARGET_LABEL"
        assert seen == []
        e = trace.of_kind(TraceEventKind.TYPED_JUDGMENT)[0]
        assert e["question"] == "target_label_rescue"
        assert e["accepted"] is False and e["chosen"] is None

    def test_nothing_is_traced_without_a_port(self) -> None:
        """救済を配線していなければ、失敗はそのままで trace に判断は残らない。"""
        trace = _RecordingTrace()
        result, _ = _call("East Shrine", port=None, trace=trace)

        assert result.success is False
        assert trace.of_kind(TraceEventKind.TYPED_JUDGMENT) == []
