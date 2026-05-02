"""ObservationTraceRecorder の分類・保存テスト。"""

from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.services.in_memory_observation_experience_trace_store import (
    InMemoryObservationExperienceTraceStore,
)
from ai_rpg_world.application.llm.services.observation_trace_recorder import (
    ObservationTraceRecorder,
    classify_observation_kind,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _entry(
    structured_type: str,
    *,
    category: str = "self_only",
    schedules_turn: bool = False,
    breaks_movement: bool = False,
    structured_extra: dict | None = None,
) -> ObservationEntry:
    structured = {"type": structured_type}
    if structured_extra:
        structured.update(structured_extra)
    return ObservationEntry(
        occurred_at=datetime.now(),
        game_time_label="Day 1 08:00",
        output=ObservationOutput(
            prose="観測した。",
            structured=structured,
            observation_category=category,  # type: ignore[arg-type]
            schedules_turn=schedules_turn,
            breaks_movement=breaks_movement,
        ),
    )


def test_classify_observation_kind_uses_structured_type() -> None:
    assert classify_observation_kind(_entry("player_spoke")) == "speech"
    assert classify_observation_kind(_entry("weather_changed")) == "environment_change"
    assert classify_observation_kind(_entry("entity_entered_spot")) == "other_agent_action"
    assert classify_observation_kind(_entry("hitbox_hit")) == "intervention_to_self"
    assert classify_observation_kind(_entry("location_entered")) == "world_event"


def test_classify_observation_kind_falls_back_to_category() -> None:
    assert (
        classify_observation_kind(_entry("unknown", category="environment"))
        == "environment_change"
    )
    assert (
        classify_observation_kind(_entry("unknown", category="social"))
        == "other_agent_action"
    )


def test_record_saves_observation_trace_with_refs_and_salience() -> None:
    store = InMemoryObservationExperienceTraceStore()
    recorder = ObservationTraceRecorder(store)
    player_id = PlayerId(1)
    entry = _entry(
        "entity_entered_spot",
        category="social",
        schedules_turn=True,
        structured_extra={
            "actor": "Alice",
            "spot_id_value": 10,
        },
    )

    trace = recorder.record(player_id, entry)

    assert trace in store.get_recent(player_id, 10)
    assert trace.agent_id == 1
    assert trace.observation_summary == "観測した。"
    assert trace.observation_kind == "other_agent_action"
    assert trace.game_time_label == "Day 1 08:00"
    assert trace.perceived_salience == "medium"
    assert "Alice" in trace.visible_agents
    assert "type:entity_entered_spot" in trace.world_event_refs
    assert "spot_id_value:10" in trace.world_event_refs
    assert trace.context_spot_id == 10


def test_record_context_spot_id_none_when_spot_id_value_not_coercible() -> None:
    store = InMemoryObservationExperienceTraceStore()
    recorder = ObservationTraceRecorder(store)
    entry = _entry(
        "entity_entered_spot",
        structured_extra={"spot_id_value": "not-an-int"},
    )
    trace = recorder.record(PlayerId(1), entry)
    assert trace.context_spot_id is None
    assert "spot_id_value:not-an-int" in trace.world_event_refs


def test_record_fills_spatial_from_runtime_when_struct_spot_missing() -> None:
    store = InMemoryObservationExperienceTraceStore()
    recorder = ObservationTraceRecorder(store)
    entry = _entry("weather_changed", category="environment")
    rtc = ToolRuntimeContextDto(
        targets={},
        current_spot_id=7,
        current_sub_location_id=42,
        current_x=1,
        current_y=2,
        current_z=3,
        current_area_ids=(99, 100),
    )
    trace = recorder.record(PlayerId(1), entry, runtime_context=rtc)
    assert trace.context_spot_id == 7
    assert trace.context_sub_location_id == 42
    assert trace.context_x == 1
    assert trace.context_y == 2
    assert trace.context_z == 3
    assert trace.context_tile_area_ids is None


def test_record_structured_spot_id_takes_precedence_over_runtime() -> None:
    store = InMemoryObservationExperienceTraceStore()
    recorder = ObservationTraceRecorder(store)
    entry = _entry(
        "entity_entered_spot",
        structured_extra={"spot_id_value": 10},
    )
    rtc = ToolRuntimeContextDto(targets={}, current_spot_id=999)
    trace = recorder.record(PlayerId(1), entry, runtime_context=rtc)
    assert trace.context_spot_id == 10
