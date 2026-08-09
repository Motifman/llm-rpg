"""world flag の実変化だけが因果を保った trace になることを保証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems.world_flags_codec import (
    WorldFlagsSubsystemCodec,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "station_drill.json"
)
_MORI = PlayerId(1)


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def record(self, kind: str, **kwargs: Any):
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


def _flag_events(recorder: _CapturingRecorder):
    return [
        event
        for event in recorder.events
        if event.kind == TraceEventKind.WORLD_FLAG_CHANGED
    ]


class TestMutableWorldFlagStateTransitions:
    """集合の差分を、変わった flag ごとの状態遷移として通知する。"""

    def test_one_replacement_emits_one_transition_for_each_changed_flag(self) -> None:
        """一度の全体置換で二つ変われば、順序の安定した二件を通知する。"""
        state = MutableWorldFlagState()
        changes = []
        state.set_change_callback(changes.append)
        context = WorldFlagMutationContext(
            source=WorldFlagMutationSource.SCENARIO_EVENT,
            actor_player_id=None,
        )

        state.replace_from_interaction(
            frozenset({"task_weather", "lights_off"}),
            context=context,
        )

        assert [
            (change.flag_name, change.is_set, change.context)
            for change in changes
        ] == [
            ("lights_off", True, context),
            ("task_weather", True, context),
        ]

    def test_reapplying_the_same_set_emits_no_duplicate_transition(self) -> None:
        """同じ集合の再設定は、既存 flag を変化として重ねて通知しない。"""
        state = MutableWorldFlagState()
        changes = []
        state.set_change_callback(changes.append)
        context = WorldFlagMutationContext(
            source=WorldFlagMutationSource.SCENARIO_EVENT,
            actor_player_id=None,
        )

        state.replace_from_interaction(frozenset({"task_weather"}), context=context)
        state.replace_from_interaction(frozenset({"task_weather"}), context=context)

        assert len(changes) == 1

    def test_removing_a_flag_emits_an_unset_transition(self) -> None:
        """既存 flag を降ろすと set=False の状態遷移を一件通知する。"""
        state = MutableWorldFlagState()
        changes = []
        state.set_change_callback(changes.append)
        context = WorldFlagMutationContext(
            source=WorldFlagMutationSource.PREPARED_ACTION,
            actor_player_id=3,
        )
        state.add("prepared:repair:3", context=context)
        changes.clear()

        state.remove("prepared:repair:3", context=context)

        assert [
            (change.flag_name, change.is_set, change.context)
            for change in changes
        ] == [("prepared:repair:3", False, context)]

    def test_mutation_context_requires_an_explicit_actor(self) -> None:
        """actor が不明でも None を明記させ、呼び出し元の渡し忘れを許さない。"""
        with pytest.raises(TypeError):
            WorldFlagMutationContext(  # type: ignore[call-arg]
                source=WorldFlagMutationSource.SCENARIO_EVENT,
            )


class TestWorldFlagTransitionTrace:
    """実 runtime の flag 変更を分析可能な payload で trace に残す。"""

    def test_station_drill_task_records_the_flag_and_actor(self) -> None:
        """モリの気象作業完了が task_weather の成立として trace に一件残る。"""
        runtime = create_world_runtime(_SCENARIO)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        for action_name in ("log_weather", "log_weather_2", "log_weather_3"):
            runtime.do_interact(_MORI, "weather_log", action_name)

        events = _flag_events(recorder)
        assert len(events) == 1
        event = events[0]
        assert event.player_id == int(_MORI)
        assert event.payload == {
            "flag_name": "task_weather",
            "set": True,
            "source": "spot_interaction",
            "actor_player_id": int(_MORI),
        }

    def test_snapshot_restore_does_not_record_past_transitions(self) -> None:
        """snapshot 復元は過去の flag 成立を新しい状態遷移として残さない。"""
        runtime = create_world_runtime(_SCENARIO)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        WorldFlagsSubsystemCodec().restore(
            runtime,
            {
                "schema_version": 1,
                "flags": ["task_weather", "task_wiring"],
            },
        )

        assert runtime._world_flag_state.as_frozen_set() == frozenset(
            {"task_weather", "task_wiring"}
        )
        assert _flag_events(recorder) == []
