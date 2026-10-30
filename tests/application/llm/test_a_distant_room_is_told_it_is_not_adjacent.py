"""隣接していない既知の場所を行き先に書いたら、「見つからない」ではなく「隣接していない」と返す。

travel_to の失敗 51 件 (83 run) のほぼ全部が、目的文や記憶にある部屋 (機関室) を隣の
場所として書いたものだった。「見つかりません」と返すと当人はその部屋が無いと誤解する。
規則で確定できることなので、意味で選び直す処理より先に確定し、Jev には問わない。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
    is_reschedulable_error_code,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
)
from ai_rpg_world.application.llm.remediation_mapping import DEFAULT_REMEDIATION_BY_ERROR_CODE
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    DESTINATION_NOT_ADJACENT,
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_label_rescue import (
    TargetLabelRescue,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    build_travel_to_invalid_label_failure,
)


class _CountingPort(ITypedJudgmentPort):
    def __init__(self) -> None:
        self.calls = 0

    def judge(self, state: str | Mapping[str, Any] | Sequence[Any], questions: Mapping[str, Question]):
        self.calls += 1
        return {
            name: JudgmentResult(
                value="通信室",
                probabilities={"通信室": 0.99},
                confidence=0.9,
                source=JudgmentSource.JEV,
                latency_ms=1.0,
            )
            for name in questions
        }


def _context(*, distant: tuple[str, ...] = ("機関室", "観測室")) -> ToolRuntimeContextDto:
    targets: dict[str, ToolRuntimeTargetDto] = {
        "S1": DestinationToolRuntimeTargetDto(
            label="S1", kind="spot_graph_destination", display_name="通信室", spot_id=4
        ),
        "S2": DestinationToolRuntimeTargetDto(
            label="S2", kind="spot_graph_destination", display_name="連絡通路", spot_id=5
        ),
    }
    return ToolRuntimeContextDto(targets=targets, distant_spot_names=distant)


def _travel(written: str, *, port: ITypedJudgmentPort | None = None, context: ToolRuntimeContextDto | None = None):
    rescue = TargetLabelRescue(port=port, min_confidence=0.85) if port else None
    return SpotGraphArgumentResolver(target_label_rescue=rescue).resolve_args(
        "travel_to", {"destination_label": written, "inner_thought": ""}, context or _context()
    )


class TestADistantRoomFailsWithItsOwnReason:
    def test_a_known_room_that_is_not_adjacent_is_named_as_such(self) -> None:
        """隣接していない既知の部屋は DESTINATION_NOT_ADJACENT で失敗し、行ける場所が並ぶ。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _travel("機関室")

        assert caught.value.error_code == DESTINATION_NOT_ADJACENT
        assert str(caught.value) == "「機関室」はここと隣接していません。有効な接続先: 通信室 / 連絡通路"

    def test_a_quoted_room_name_is_recognised_too(self) -> None:
        """引用符つきで書いても、同じ理由で失敗する。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _travel('"機関室"')

        assert caught.value.error_code == DESTINATION_NOT_ADJACENT

    def test_jev_is_not_asked_about_a_distant_room(self) -> None:
        """救済が配線されていても、隣接していない部屋は Jev に問わない。途中の部屋に置き換えない。"""
        port = _CountingPort()

        with pytest.raises(ToolArgumentResolutionException) as caught:
            _travel("機関室", port=port)

        assert caught.value.error_code == DESTINATION_NOT_ADJACENT
        assert port.calls == 0

    def test_an_unknown_name_still_reaches_jev(self) -> None:
        """世界に無い名前は従来どおり候補から選び直される (正の対照)。"""
        port = _CountingPort()

        out = _travel("通信の部屋", port=port)

        assert out["destination_spot_id"] == 4
        assert port.calls == 1

    def test_an_adjacent_room_is_resolved_even_if_listed_as_distant(self) -> None:
        """隣の場所として引ける名前は、遠い場所の一覧に紛れていても普通に解決する。"""
        out = _travel("通信室", context=_context(distant=("通信室", "機関室")))

        assert out["destination_spot_id"] == 4

    def test_without_distant_names_the_failure_is_unchanged(self) -> None:
        """遠い場所の名前を持たない配線では、従来の INVALID_DESTINATION_LABEL のまま。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _travel("機関室", context=_context(distant=()))

        assert caught.value.error_code == "INVALID_DESTINATION_LABEL"


class TestTheCodeIsWiredEverywhereAFailureCodeMustBe:
    def test_the_travel_to_builder_keeps_the_reason(self) -> None:
        """travel_to 専用の失敗組み立ては、この理由を「見つかりません」で上書きしない。"""
        with pytest.raises(ToolArgumentResolutionException) as caught:
            _travel("機関室")

        result = build_travel_to_invalid_label_failure(_context(), {"destination_label": "機関室"}, caught.value)

        assert result.error_code == DESTINATION_NOT_ADJACENT
        assert result.message.startswith("「機関室」はここと隣接していません。")
        assert "隣の場所" in result.remediation

    def test_the_code_has_a_remediation_and_is_rescheduled(self) -> None:
        """失敗コードには復帰の案内があり、次のターンで隣の場所を選び直せるよう再スケジュールされる。"""
        assert DESTINATION_NOT_ADJACENT in DEFAULT_REMEDIATION_BY_ERROR_CODE
        assert is_reschedulable_error_code(DESTINATION_NOT_ADJACENT)
