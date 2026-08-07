"""tool に渡せる値は本文で引用符つきになることを保証する。

run 016 / 017 では、action_name と意味ラベルが同じ括弧に入り、
LLM がラベルや装飾込みの行を action_name に送った。表示と
tool_runtime_context を同時に作る入口で照合し、書き忘れも止める。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services import spot_graph_ui_context_builder
from ai_rpg_world.application.llm.services.prompt_argument_contract import (
    PromptArgumentContractError,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)


class _CapturingRecorder:
    """受け取った trace をメモリ上に保持する。"""

    def __init__(self) -> None:
        self.events: list = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        self.events.append((kind, tick, player_id, payload))

    def close(self) -> None:
        pass


def _render_action_without_quotes(action_name, hints, *, display_label="") -> str:
    """境界検査を試すため、変更前と同じ裸の action_name を返す変異。"""
    label = str(display_label or "").strip()
    return f"{label} ({action_name})" if label else str(action_name)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def test_startup_rejects_an_action_name_rendered_without_quotes(monkeypatch) -> None:
    """整形側が action_name の引用符を落とすと、全 player 検査が起動を止める。"""
    monkeypatch.setattr(
        spot_graph_ui_context_builder,
        "format_action_display_with_hints",
        _render_action_without_quotes,
    )

    with pytest.raises(PromptArgumentContractError, match="read_board"):
        create_world_runtime(_SCENARIO)


def test_startup_rejects_a_connection_name_rendered_without_quotes(
    monkeypatch,
) -> None:
    """整形側が接続名の引用符を落としても、全 player 検査が起動を止める。"""
    monkeypatch.setattr(
        spot_graph_ui_context_builder,
        "quote_tool_argument",
        lambda value: str(value),
    )

    with pytest.raises(PromptArgumentContractError, match="集会室の扉"):
        create_world_runtime(_SCENARIO)


def test_runtime_violation_is_traced_without_aborting_the_run(monkeypatch) -> None:
    """run 中に生じた表記破れは例外にせず、player と候補値を trace に残す。"""
    runtime = create_world_runtime(_SCENARIO)
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)
    monkeypatch.setattr(
        spot_graph_ui_context_builder,
        "format_action_display_with_hints",
        _render_action_without_quotes,
    )

    result = runtime.build_llm_context(_MORI)

    assert result.current_state_text
    events = [
        event
        for event in recorder.events
        if event[0] == TraceEventKind.PROMPT_ARGUMENT_CONTRACT_VIOLATION
    ]
    assert len(events) == 1
    assert events[0][2] == _MORI.value
    assert any(
        violation["value"] == "read_board"
        for violation in events[0][3]["violations"]
    )


def test_a_dark_hidden_object_is_not_registered_as_a_target() -> None:
    """暗所で見えない物体は失敗理由用の名前だけを持ち、引数候補には入らない。"""
    runtime = create_world_runtime(_SCENARIO)
    _move(runtime, _MORI, "corridor")

    context = runtime.build_llm_context(_MORI).tool_runtime_context

    assert context.dark_hidden_object_names
    hidden = set(context.dark_hidden_object_names)
    assert hidden.isdisjoint(
        target.display_name for target in context.targets.values()
    )


def test_a_world_starting_in_darkness_passes_startup_validation(tmp_path: Path) -> None:
    """初期地点の暗所物体は候補に入らず、除外リストなしでも起動できる。"""
    scenario = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    scenario["players"][0]["spawn_spot"] = "corridor"
    path = tmp_path / "station_drill_dark_start.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    runtime = create_world_runtime(path)

    context = runtime.build_llm_context(_MORI).tool_runtime_context
    assert context.dark_hidden_object_names
