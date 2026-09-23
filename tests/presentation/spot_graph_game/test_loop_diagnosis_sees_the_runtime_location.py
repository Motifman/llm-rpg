"""本番の session で、ループ警告の見立ての材料の居場所が world runtime から来る (#1411)。

見立ての単体試験は居場所を lambda で渡すので、本番の配線 (``location_provider``) を
外しても通る。配線を呼び忘れると、「状態の取り違え」の文面が居場所を言えなくなる
(design_decisions #41)。そのため本番と同じ入口から session を組んで確かめる。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class _Trace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[no-untyped-def]
        self.events.append({"kind": kind, "player_id": player_id, **payload})


class TestTheDiagnosisSeesTheRuntimeLocation:
    """見立ての state の居場所が、runtime の現在地と一致することを保証する。"""

    def test_the_diagnosis_state_carries_the_spot_the_runtime_reports(self) -> None:
        """同じ移動を 2 回失敗させると、見立ての state の current_location が runtime の現在地と一致する。"""
        with TemporaryDirectory() as tmp:
            manager = GameRuntimeManager(
                scenarios_dir=_SCENARIO.parent,
                characters_path=Path(tmp) / "characters.json",
                runtime_config=ResolvedLlmRuntimeConfig.for_tests(
                    typed_judgment_provider="stub",
                    typed_judgment_loop_diagnosis_enabled=True,
                ),
            )
            character = manager.create_character(CharacterCreateRequest(name="probe"))
            summary = manager.create_session(
                SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id])
            )
            wiring = manager._sessions[summary.session_id].llm_wiring
            trace = _Trace()
            wiring.runtime.set_trace_recorder(trace)
            player = PlayerId.create(1)

            for _ in range(2):
                wiring.tool_call_loop_guard.record_and_check(
                    player, "travel_to", {"destination_label": "存在しない岬"},
                    success=False, error_code="INVALID_DESTINATION_LABEL",
                    result_summary="移動先が見つかりません",
                )

            [judgment] = [
                e for e in trace.events
                if e["kind"] == TraceEventKind.TYPED_JUDGMENT
                and e.get("question") == "loop_diagnosis"
            ]
            assert judgment["state"]["current_location"] == wiring.runtime.get_player_spot_name(player)
