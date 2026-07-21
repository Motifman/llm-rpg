"""常時遠景が current state prompt にだけ入る実配線を保証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import runtime_config


_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_V3 = _SCENARIOS_DIR / "survival_island_v3_coop.json"
_V4 = _SCENARIOS_DIR / "survival_island_v4_coop.json"


class _TraceRecorderSpy:
    """record() の呼び出しを保持する最小 spy。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, *, tick=None, player_id=None, **payload):  # noqa: ANN001
        self.events.append(
            (
                str(kind),
                {"tick": tick, "player_id": player_id, **payload},
            )
        )

    def close(self) -> None:
        pass


class TestDistantViewRuntimePrompt:
    """create_world_runtime から build_llm_context までの遠景 prompt 配線。"""

    def test_v4_initial_prompt_renders_distant_view_without_area_id(self) -> None:
        """v4 の初期浜辺では山影と森が現在地説明直後に出て、area_id は出ない。"""
        runtime = create_world_runtime(_V4, config=runtime_config())

        text = runtime.build_llm_context(PlayerId(1)).current_state_text

        assert "北東の遠くに切り立った山影が見える。" in text
        assert "北に深い森の緑が見える。" in text
        assert "mountain" not in text
        assert "forest" not in text
        assert "area_id" not in text

        lines = text.splitlines()
        description_index = next(
            i for i, line in enumerate(lines) if line.startswith("  嵐で打ち上げられた")
        )
        assert lines[description_index + 1] == "  北東の遠くに切り立った山影が見える。"

    def test_scenario_without_areas_keeps_distant_view_empty(self) -> None:
        """areas 未定義の既存シナリオでは常時遠景を出さず、現行 prompt を汚さない。"""
        runtime = create_world_runtime(_V3, config=runtime_config())

        text = runtime.build_llm_context(PlayerId(1)).current_state_text

        assert "北東の遠くに切り立った山影が見える。" not in text
        assert "遠景:" not in text


class TestDistantViewRuntimeTrace:
    """現在状態系の遠景 trace が既定で出ず、明示時だけ出ることを固定する。"""

    def test_trace_is_not_recorded_by_default(self) -> None:
        """DISTANT_VIEW_TRACE_ENABLED が false なら prompt build 時に遠景 trace は出ない。"""
        runtime = create_world_runtime(_V4, config=runtime_config())
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_llm_context(PlayerId(1))

        kinds = [kind for kind, _ in recorder.events]
        assert TraceEventKind.DISTANT_VIEW_RENDERED not in kinds
        assert TraceEventKind.DISTANT_VIEW_SKIPPED not in kinds

    def test_trace_records_rendered_payload_when_enabled(self) -> None:
        """trace 有効時は rendered area と閾値を構造化 payload に残す。"""
        runtime = create_world_runtime(
            _V4,
            config=runtime_config(distant_view_trace_enabled=True),
        )
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_llm_context(PlayerId(1))

        events = [
            payload
            for kind, payload in recorder.events
            if kind == TraceEventKind.DISTANT_VIEW_RENDERED
        ]
        assert len(events) == 1
        payload = events[0]
        assert payload["player_id"] == 1
        assert payload["rendered_area_ids"] == ["mountain", "forest"]
        assert payload["rendered_count"] == 2
        assert payload["thresholds"]["score"] == 0.20
