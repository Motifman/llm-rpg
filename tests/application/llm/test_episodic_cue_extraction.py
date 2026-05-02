"""P2: ルールベース episodic cue 抽出の決定論・マージ・上限。"""

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodicCue,
    ObservationExperienceTrace,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.episodic_cue_extraction import (
    MAX_EPISODIC_CUES_PER_EPISODE,
    episodic_cues_from_action_trace,
    episodic_cues_from_observation_trace,
    episodic_cues_from_tool_runtime_context,
    episodic_cues_from_traces,
    merge_episodic_cues,
    validate_episodic_cues,
)


def _action(
    *,
    tool_name: str = "spot_graph_look",
    spot: int | None = 12,
    areas: tuple[int, ...] | None = (3, 3),
    sub: int | None = 7,
) -> ActionExperienceTrace:
    return ActionExperienceTrace(
        trace_id="a1",
        agent_id=1,
        occurred_at=datetime.now(),
        tool_name=tool_name,
        tool_args={},
        inner_thought="t",
        intention="i",
        expected_result="e",
        attention="a",
        emotion_hint="curiosity",
        tool_result="ok",
        result_success=True,
        context_spot_id=spot,
        context_tile_area_ids=areas,
        context_sub_location_id=sub,
    )


def test_action_trace_spatial_and_action_cues_deterministic() -> None:
    t = _action(tool_name="foo_bar")
    cues = episodic_cues_from_action_trace(t)
    canonical = [c.to_canonical() for c in cues]
    assert "action:foo_bar" in canonical
    assert "place_spot:12" in canonical
    assert "tile_area:3" in canonical
    assert "sub_loc:7" in canonical


def test_observation_trace_structured_ids() -> None:
    o = ObservationExperienceTrace(
        trace_id="o1",
        agent_id=1,
        occurred_at=datetime.now(),
        observation_summary="s",
        observation_kind="world_event",
        structured={
            "type": "noise",
            "spot_id_value": 99,
            "world_object_id_value": 42,
        },
        context_spot_id=None,
    )
    cues = episodic_cues_from_observation_trace(o)
    canon = {c.to_canonical() for c in cues}
    assert "observation_kind:world_event" in canon
    assert "place_spot:99" in canon
    assert "world_object:42" in canon


def test_observation_prefers_context_spot_over_structured() -> None:
    o = ObservationExperienceTrace(
        trace_id="o1",
        agent_id=1,
        occurred_at=datetime.now(),
        observation_summary="s",
        observation_kind="world_event",
        structured={"spot_id_value": 99},
        context_spot_id=5,
    )
    cues = episodic_cues_from_observation_trace(o)
    spots = [c for c in cues if c.axis == "place_spot"]
    assert len(spots) == 1 and spots[0].value == "5"


def test_runtime_context_merges_targets() -> None:
    tgt = ToolRuntimeTargetDto(
        label="x",
        kind="chest",
        display_name="Chest",
        world_object_id=100,
        interaction_type="open",
    )
    ctx = ToolRuntimeContextDto(
        targets={"x": tgt},
        current_spot_id=1,
        current_sub_location_id=2,
        current_area_ids=(10,),
    )
    cues = episodic_cues_from_tool_runtime_context(ctx)
    canon = {c.to_canonical() for c in cues}
    assert "place_spot:1" in canon
    assert "sub_loc:2" in canon
    assert "tile_area:10" in canon
    assert "object_type:chest" in canon
    assert "object_category:open" in canon
    assert "world_object:100" in canon


def test_observation_trace_accepts_string_ids_in_structured() -> None:
    o = ObservationExperienceTrace(
        trace_id="o1",
        agent_id=1,
        occurred_at=datetime.now(),
        observation_summary="s",
        observation_kind="world_event",
        structured={"spot_id_value": "88", "world_object_id_value": "5"},
        context_spot_id=None,
    )
    cues = episodic_cues_from_observation_trace(o)
    canon = {c.to_canonical() for c in cues}
    assert "place_spot:88" in canon
    assert "world_object:5" in canon


def test_merge_episodic_cues_order_and_dedupe() -> None:
    a = (
        EpisodicCue("place_spot", "1"),
        EpisodicCue("tile_area", "2"),
        EpisodicCue("place_spot", "1"),
    )
    b = (EpisodicCue("tile_area", "2"), EpisodicCue("action", "x"))
    m = merge_episodic_cues(a, b)
    assert [c.to_canonical() for c in m] == [
        "place_spot:1",
        "tile_area:2",
        "action:x",
    ]


def test_episodic_cues_from_traces_respects_cap() -> None:
    many = tuple(
        _action(tool_name=f"t{i}", spot=i, areas=None, sub=None)
        for i in range(MAX_EPISODIC_CUES_PER_EPISODE + 8)
    )
    cues = episodic_cues_from_traces(many)
    assert len(cues) <= MAX_EPISODIC_CUES_PER_EPISODE


def test_validate_episodic_cues_drops_long_values() -> None:
    long_val = "x" * 200
    cues = (
        EpisodicCue("action", "ok"),
        EpisodicCue("foo", long_val),
    )
    v = validate_episodic_cues(cues)
    assert len(v) == 1 and v[0].axis == "action"
