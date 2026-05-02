"""ObservationTraceRecordingBuffer のテスト。"""

from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.services.in_memory_observation_experience_trace_store import (
    InMemoryObservationExperienceTraceStore,
)
from ai_rpg_world.application.llm.services.observation_trace_recorder import (
    ObservationTraceRecorder,
)
from ai_rpg_world.application.llm.services.observation_trace_recording_buffer import (
    ObservationTraceRecordingBuffer,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def test_append_records_trace_and_keeps_buffer_behavior() -> None:
    player_id = PlayerId(1)
    trace_store = InMemoryObservationExperienceTraceStore()
    inner = DefaultObservationContextBuffer()
    buffer = ObservationTraceRecordingBuffer(
        inner=inner,
        recorder=ObservationTraceRecorder(trace_store),
    )
    entry = ObservationEntry(
        occurred_at=datetime.now(),
        output=ObservationOutput(
            prose="天気が変わった。",
            structured={"type": "weather_changed", "spot_id_value": 1},
            observation_category="environment",
        ),
    )

    buffer.append(player_id, entry)

    assert buffer.get_observations(player_id) == [entry]
    assert buffer.drain(player_id) == [entry]
    assert buffer.get_observations(player_id) == []
    traces = trace_store.get_recent(player_id, 10)
    assert len(traces) == 1
    assert traces[0].observation_kind == "environment_change"
    assert traces[0].observation_summary == "天気が変わった。"


def test_append_passes_runtime_context_to_trace() -> None:
    player_id = PlayerId(1)
    trace_store = InMemoryObservationExperienceTraceStore()
    inner = DefaultObservationContextBuffer()
    buffer = ObservationTraceRecordingBuffer(
        inner=inner,
        recorder=ObservationTraceRecorder(trace_store),
    )
    entry = ObservationEntry(
        occurred_at=datetime.now(),
        output=ObservationOutput(
            prose="他者の行動。",
            structured={"type": "entity_entered_spot"},
            observation_category="social",
        ),
    )
    rtc = ToolRuntimeContextDto(
        targets={},
        current_spot_id=55,
        current_sub_location_id=3,
        current_x=0,
        current_y=0,
        current_z=0,
    )
    buffer.append(player_id, entry, runtime_context=rtc)
    traces = trace_store.get_recent(player_id, 10)
    assert len(traces) == 1
    assert traces[0].context_spot_id == 55
    assert traces[0].context_sub_location_id == 3
