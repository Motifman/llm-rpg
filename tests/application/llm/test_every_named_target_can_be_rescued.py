"""名前で対象を引く全ツールで、候補があるのに当たらない名前は同じ入口で意味により選び直される。

段は 3 つ。表示名で当たる・別の種別に在る・同名が複数は規則で確定する (#228)。どこにも
無く候補が空なら問わずに失敗する。どこにも無く候補があるときだけ Jev に「該当なし」を
含めて問い、採れば置き換えて結果文の先頭で当人に見せ、採らなくても判断は trace に残す。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    LlmCommandResultDto,
    PlayerToolRuntimeTargetDto,
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
    TARGET_LABEL_JUDGMENTS_KEY,
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_label_rescue import (
    NO_MATCH_OPTION,
    TargetLabelRescue,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    adapt_executor_handler_with_resolver,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_GIVE_ITEM
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _ScriptedPort(ITypedJudgmentPort):
    """書かれた名前ごとに決まった選択肢を返す。渡された state を記録する。"""

    def __init__(self, answers: Mapping[str, str], probability: float = 0.95) -> None:
        self._answers, self._probability = dict(answers), probability
        self.states: list[Mapping[str, Any]] = []

    def judge(self, state: str | Mapping[str, Any] | Sequence[Any], questions: Mapping[str, Question]):
        assert isinstance(state, Mapping)
        self.states.append(state)
        chosen = self._answers.get(str(state["written_target_name"]), NO_MATCH_OPTION)
        return {
            name: JudgmentResult(
                value=chosen,
                probabilities={chosen: self._probability},
                confidence=0.9,
                source=JudgmentSource.JEV,
                latency_ms=5.0,
            )
            for name in questions
        }


class _RecordingTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        self.events.append({"kind": kind, "tick": tick, "player_id": player_id, **payload})


def _context(*, ground: bool = True) -> ToolRuntimeContextDto:
    targets: dict[str, ToolRuntimeTargetDto] = {
        "I1": InventoryToolRuntimeTargetDto(
            label="I1", kind="inventory_item", display_name="干し肉", item_instance_id=41
        ),
        "I2": InventoryToolRuntimeTargetDto(
            label="I2", kind="inventory_item", display_name="真水", item_instance_id=42
        ),
        "S1": DestinationToolRuntimeTargetDto(
            label="S1", kind="spot_graph_destination", display_name="麦畑", spot_id=7
        ),
        "S2": DestinationToolRuntimeTargetDto(
            label="S2", kind="spot_graph_destination", display_name="薬草の土手", spot_id=8
        ),
        "SL1": ToolRuntimeTargetDto(
            label="SL1", kind="spot_graph_sub_location", display_name="祭壇前", sub_location_id=2
        ),
        "P1": PlayerToolRuntimeTargetDto(label="P1", kind="spot_graph_player", display_name="ガレン", player_id=2),
        "P2": PlayerToolRuntimeTargetDto(label="P2", kind="spot_graph_player", display_name="ドナ", player_id=3),
    }
    if ground:
        targets["G1"] = InventoryToolRuntimeTargetDto(
            label="G1", kind="ground_item", display_name="流木", real_item_instance_id=51
        )
    return ToolRuntimeContextDto(targets=targets)


def _resolver(port: ITypedJudgmentPort) -> SpotGraphArgumentResolver:
    return SpotGraphArgumentResolver(target_label_rescue=TargetLabelRescue(port=port, min_confidence=0.85))


class TestEachToolAsksAboutAnUnmatchedName:
    def test_use_item_replaces_a_misspelt_held_item(self) -> None:
        """use_item の品名が候補に無いとき、Jev が選んだ手持ちの品に置き換わり、判断が列で運ばれる。"""
        port = _ScriptedPort({"乾し肉": "干し肉"})

        out = _resolver(port).resolve_args(
            "use_item", {"item_label": "乾し肉", "inner_thought": "腹が減った"}, _context()
        )

        assert out["item_spec_id"] == 41
        (judgment,) = out[TARGET_LABEL_JUDGMENTS_KEY]
        assert judgment["tool"] == "use_item" and judgment["argument"] == "使用するアイテム名"
        assert judgment["original"] == "乾し肉" and judgment["replaced_with"] == "干し肉"

    def test_the_state_tells_jev_which_tool_and_argument_the_name_was_written_for(self) -> None:
        """Jev に渡す state には、書かれた名前・ツール・引数名・候補が入り、整数 ID は入らない。"""
        port = _ScriptedPort({"乾し肉": "干し肉"})

        _resolver(port).resolve_args("use_item", {"item_label": "乾し肉", "inner_thought": ""}, _context())

        (state,) = port.states
        assert state["tool"] == "use_item" and state["argument"] == "使用するアイテム名"
        assert set(state["candidates"]) == {"干し肉", "真水"}
        assert "41" not in repr(state)

    def test_pickup_item_replaces_a_paraphrased_ground_item(self) -> None:
        """pickup_item の名前が候補に無いとき、Jev が選んだ足元の品に置き換わる。"""
        port = _ScriptedPort({"漂着した流木": "流木"})

        out = _resolver(port).resolve_args(
            "pickup_item", {"ground_item_label": "漂着した流木", "inner_thought": ""}, _context()
        )

        assert out["item_instance_id"] == 51
        assert out[TARGET_LABEL_JUDGMENTS_KEY][0]["tool"] == "pickup_item"

    def test_travel_to_replaces_a_variant_character_destination(self) -> None:
        """travel_to の行き先が候補に無いとき (異体字)、Jev が選んだ隣の場所に置き換わる。"""
        port = _ScriptedPort({"麥畑": "麦畑"})

        out = _resolver(port).resolve_args("travel_to", {"destination_label": "麥畑", "inner_thought": ""}, _context())

        assert out["destination_spot_id"] == 7
        assert out[TARGET_LABEL_JUDGMENTS_KEY][0]["tool"] == "travel_to"

    def test_drop_item_uses_the_same_entry(self) -> None:
        """drop_item も同じ入口を通る。"""
        port = _ScriptedPort({"乾し肉": "干し肉"})

        out = _resolver(port).resolve_args("drop_item", {"item_label": "乾し肉", "inner_thought": ""}, _context())

        assert out["item_spec_id"] == 41


class TestWhenTheNameIsNotAskedAbout:
    def test_an_empty_candidate_list_is_not_asked_about(self) -> None:
        """足元に何も無ければ問わずに失敗する。選び直す先が無い。"""
        port = _ScriptedPort({})

        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolver(port).resolve_args(
                "pickup_item", {"ground_item_label": "流木", "inner_thought": ""}, _context(ground=False)
            )

        assert caught.value.error_code == "INVALID_TARGET_LABEL"
        assert port.states == []

    def test_a_name_of_another_kind_is_not_asked_about(self) -> None:
        """区画の名前を行き先に書いたときは種類違いで決まり、Jev には問わない。"""
        port = _ScriptedPort({"祭壇前": "麦畑"})

        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolver(port).resolve_args("travel_to", {"destination_label": "祭壇前", "inner_thought": ""}, _context())

        assert caught.value.error_code == "INVALID_DESTINATION_KIND"
        assert port.states == []

    def test_a_no_match_answer_keeps_travel_to_failing_with_the_destination_code(self) -> None:
        """隣接していない部屋を書いて Jev が該当なしと言えば、INVALID_DESTINATION_LABEL のまま失敗し判断が例外に載る。"""
        port = _ScriptedPort({})

        with pytest.raises(ToolArgumentResolutionException) as caught:
            _resolver(port).resolve_args("travel_to", {"destination_label": "機関室", "inner_thought": ""}, _context())

        assert caught.value.error_code == "INVALID_DESTINATION_LABEL"
        assert caught.value.judgment is not None
        assert caught.value.judgment["accepted"] is False and caught.value.judgment["tool"] == "travel_to"


class TestGiveItemCarriesEveryJudgment:
    def test_both_the_item_and_the_recipient_can_be_rescued_in_one_entry(self) -> None:
        """1 つの entry で品と相手の両方を選び直し、判断は 2 件とも列に載る。"""
        port = _ScriptedPort({"乾し肉": "干し肉", "ガレンさん": "ガレン"})

        out = _resolver(port).resolve_args(
            "give_item",
            {"gives": [{"item_label": "乾し肉", "target_player_label": "ガレンさん"}], "inner_thought": ""},
            _context(),
        )

        entry = out["gives_resolved"][0]
        assert entry["item_spec_id"] == 41 and entry["target_player_id"] == 2
        assert [(j["argument"], j["replaced_with"]) for j in out[TARGET_LABEL_JUDGMENTS_KEY]] == [
            ("渡すアイテム名", "干し肉"),
            ("相手の名前", "ガレン"),
        ]

    def test_a_rejected_entry_keeps_its_judgment_while_another_entry_succeeds(self) -> None:
        """片方の entry が該当なしで失敗しても、その判断は列に残り、他方は成功する。"""
        port = _ScriptedPort({"乾し肉": "干し肉"})

        out = _resolver(port).resolve_args(
            "give_item",
            {
                "gives": [
                    {"item_label": "乾し肉", "target_player_label": "ガレン"},
                    {"item_label": "真水", "target_player_label": "ユノ"},
                ],
                "inner_thought": "",
            },
            _context(),
        )

        ok, ng = out["gives_resolved"]
        assert ok["target_player_id"] == 2
        assert ng["error_code"] == "INVALID_TARGET_LABEL"
        judgments = out[TARGET_LABEL_JUDGMENTS_KEY]
        assert [j["accepted"] for j in judgments] == [True, False]
        assert judgments[1]["original"] == "ユノ" and judgments[1]["argument"] == "相手の名前"


class TestTheDispatchShowsAndTracesEveryJudgment:
    def test_every_judgment_is_traced_and_each_accepted_one_is_explained(self) -> None:
        """判断は 1 件ずつ trace に残り (tool と argument つき)、採った分だけ結果文の先頭に注釈が付く。"""
        port = _ScriptedPort({"乾し肉": "干し肉", "ガレンさん": "ガレン"})
        trace = _RecordingTrace()

        def raw(_pid: int, _resolved: dict[str, Any], _ctx: Any) -> LlmCommandResultDto:
            return LlmCommandResultDto(success=True, message="渡した")

        handler = adapt_executor_handler_with_resolver(
            raw,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            _resolver(port),
            trace_recorder_provider=lambda: trace,
            current_tick_provider=lambda: 4,
        )
        result = handler(
            PlayerId(1),
            {
                "gives": [
                    {"item_label": "乾し肉", "target_player_label": "ガレンさん"},
                    {"item_label": "真水", "target_player_label": "ユノ"},
                ],
                "inner_thought": "",
            },
            _context(),
        )

        events = [e for e in trace.events if e["kind"] == TraceEventKind.TYPED_JUDGMENT]
        assert [(e["tool"], e["argument"], e["accepted"]) for e in events] == [
            ("give_item", "渡すアイテム名", True),
            ("give_item", "相手の名前", True),
            ("give_item", "相手の名前", False),
        ]
        assert result.message.startswith("「乾し肉」は「干し肉」と解釈した。 「ガレンさん」は「ガレン」と解釈した。")
