"""profile で書き起こしを有効にした世界の runtime が、畳むときと環境を離れるときにエピソードを書くことを保証する (#1626)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_ISLAND = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island_v4_coop.json"
_BASE = datetime(2026, 6, 1, tzinfo=timezone.utc)


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _runtime(enabled: bool):
    values = {
        "SHORT_TERM_MEMORY_KIND": "rolling_summary",
        "SHORT_TERM_MEMORY_TURN_CAP": "2",
        "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT": "1",
    }
    if enabled:
        values["BEING_EPISODE_WRITING_ENABLED"] = "1"
    runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.from_mapping(values=values))
    recorder = _Recorder()
    runtime.set_trace_recorder(recorder)
    return runtime, recorder


def _observe(runtime, pid, prose: str, minute: int) -> None:
    runtime._short_term_memory.append(
        pid,
        ObservationEntry(
            occurred_at=_BASE + timedelta(minutes=minute),
            game_time_label=f"朝 6:{minute:02d}",
            output=ObservationOutput(prose=prose, structured={}),
        ),
    )


def _being_of(runtime, pid):
    return runtime.aux_being_resolver.resolve_being_id(runtime.aux_being_default_world_id, pid)


class TestEpisodeWritingInTheRuntime:
    """書き起こしの設定が、世界の runtime で畳むときと環境を離れるときの 2 か所に繋がっていることを保証する。"""

    def test_compaction_writes_episodes_for_the_compacted_turns(self) -> None:
        """短期記憶が古いターンを畳むと、その Being のエピソードが記録に入り、畳んだきっかけで trace に残る。"""
        runtime, recorder = _runtime(enabled=True)
        pid = runtime.get_player_ids()[0]

        _observe(runtime, pid, "浜で流木を拾った。", 1)
        runtime._short_term_memory.complete_turn(pid)
        runtime._short_term_memory.complete_turn(pid)

        episodes = runtime._being_episode_store.list_by_being(_being_of(runtime, pid))
        assert len(episodes) == 1
        assert episodes[0].environment_name == runtime.scenario.metadata.title
        writes = [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_WRITING]
        assert [(p["trigger"], p["outcome"], p["event_count"]) for p in writes] == [("compaction", "written", 1)]

    def test_leaving_writes_episodes_from_what_was_not_compacted(self) -> None:
        """環境を離れるとき、まだ畳まれていない出来事からエピソードを書き、プレイヤーごとに trace に残す。"""
        runtime, recorder = _runtime(enabled=True)
        first, *others = runtime.get_player_ids()

        _observe(runtime, first, "火がついた。", 1)
        runtime.write_episodes_on_leaving()

        assert len(runtime._being_episode_store.list_by_being(_being_of(runtime, first))) == 1
        writes = {pid: p for k, pid, p in recorder.events if k == TraceEventKind.EPISODE_WRITING}
        assert writes[int(first.value)]["trigger"] == "leaving"
        assert writes[int(first.value)]["outcome"] == "written"
        assert all(writes[int(o.value)]["skip_reason"] == "no_events" for o in others)

    def test_leaving_with_a_skip_reason_records_it_without_writing(self) -> None:
        """離れるときに飛ばす理由を渡すと、出来事が残っていても書かず、プレイヤーごとにその理由を残す。"""
        runtime, recorder = _runtime(enabled=True)
        first = runtime.get_player_ids()[0]

        _observe(runtime, first, "火がついた。", 1)
        runtime.write_episodes_on_leaving(skip_reason="llm_unusable")

        assert runtime._being_episode_store.list_by_being(_being_of(runtime, first)) == ()
        writes = [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_WRITING]
        assert len(writes) == len(runtime.get_player_ids())
        assert {(p["trigger"], p["outcome"], p["skip_reason"]) for p in writes} == {("leaving", "skipped", "llm_unusable")}

    def test_disabled_profile_writes_nothing(self) -> None:
        """有効にしていなければ、畳んでも離れても、エピソードも書き起こしの trace も出ない。"""
        runtime, recorder = _runtime(enabled=False)
        pid = runtime.get_player_ids()[0]

        _observe(runtime, pid, "浜で流木を拾った。", 1)
        runtime._short_term_memory.complete_turn(pid)
        runtime._short_term_memory.complete_turn(pid)
        _observe(runtime, pid, "火がついた。", 2)
        runtime.write_episodes_on_leaving()

        assert runtime._being_episode_store.list_by_being(_being_of(runtime, pid)) == ()
        assert all(k != TraceEventKind.EPISODE_WRITING for k, _, _ in recorder.events)
