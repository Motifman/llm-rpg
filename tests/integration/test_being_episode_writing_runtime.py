"""世界の runtime が、Being の短期記憶の範囲が埋まったときと環境を離れるときに、Being の短期記憶からエピソードを書くことを保証する (#1626、design_decisions D1824-21、D1824-23)。書き起こしは設定で止められない (#1631)。"""

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
from ai_rpg_world.being.domain.short_term_memory import RECENT_TURNS

_ISLAND = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island_v4_coop.json"
_BASE = datetime(2026, 6, 1, tzinfo=timezone.utc)


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _runtime():
    runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.from_mapping(values={}))
    recorder = _Recorder()
    runtime.set_trace_recorder(recorder)
    return runtime, recorder


def _observe(runtime, pid, prose: str, minute: int) -> None:
    runtime._recent_event_store.append_observation(
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
    """書き起こしが、世界の runtime で、Being の短期記憶の範囲が埋まったときと環境を離れるときに繋がっていることを保証する。"""

    def test_end_being_turn_writes_episodes_when_the_range_is_filled(self) -> None:
        """Being の記憶のターンが 20 に届いたところで end_being_turn を呼ぶと、範囲が埋まり、その Being の結果を反映したときにエピソードが記録に入る。"""
        from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard

        runtime, recorder = _runtime()
        pid = runtime.get_player_ids()[0]
        being_id = _being_of(runtime, pid)
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        memory.perceive(
            Observation(
                body="浜で流木を拾った。",
                route=SeenOrHeard(),
                time=ObservedTime(display="朝 6:01"),
                subject_is_self=False,
                subject_name=UNKNOWN,
                source=UNKNOWN,
                place=UNKNOWN,
                addressed_to_self=UNKNOWN,
            ),
            current_turn=0,
        )
        store.save(memory)
        for _ in range(RECENT_TURNS):
            runtime.advance_memory_turn(pid)

        runtime.end_being_turn(pid)
        runtime.async_event_executor.shutdown(timeout=5)
        runtime.apply_async_results(pid)

        (episode,) = runtime._being_episode_store.list_by_being(being_id)
        assert (episode.environment_name, episode.written_turn) == (runtime.scenario.metadata.title, RECENT_TURNS)
        assert [k for k, _, _ in recorder.events if k == TraceEventKind.BEING_SHORT_TERM_MEMORY_RANGE_FILLED] != []

    def test_leaving_writes_episodes_from_the_being_short_term_memory(self) -> None:
        """環境を離れるとき、Being の短期記憶のまだまとめていない出来事からエピソードを書き、プレイヤーごとに trace に残す。出来事の無いプレイヤーは no_events で飛ばす。"""
        runtime, recorder = _runtime()
        first, *others = runtime.get_player_ids()

        _observe(runtime, first, "火がついた。", 1)
        runtime.write_episodes_on_leaving()

        assert len(runtime._being_episode_store.list_by_being(_being_of(runtime, first))) == 1
        writes = {pid: p for k, pid, p in recorder.events if k == TraceEventKind.EPISODE_WRITING}
        assert writes[int(first.value)]["trigger"] == "leaving"
        assert writes[int(first.value)]["outcome"] == "written"
        assert all(writes[int(o.value)]["skip_reason"] == "no_events" for o in others)

    def test_leaving_does_not_rewrite_the_range_written_when_it_filled(self) -> None:
        """範囲が埋まってエピソードを書いたあとで環境を離れると、書き手に渡すのは埋まった範囲 (ターン 10 まで) より後の出来事だけになる。いきさつが届いていても待ったままでも同じ数になる。待ったままの境界は短期記憶と WriteEpisodesOnLeaving の試験が見る。"""
        from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard

        runtime, recorder = _runtime()
        pid = runtime.get_player_ids()[0]
        being_id = _being_of(runtime, pid)
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        for turn in range(1, RECENT_TURNS + 1):
            memory.perceive(
                Observation(
                    body=f"ターン {turn} の出来事",
                    route=SeenOrHeard(),
                    time=ObservedTime(display="朝 6:01"),
                    subject_is_self=False,
                    subject_name=UNKNOWN,
                    source=UNKNOWN,
                    place=UNKNOWN,
                    addressed_to_self=UNKNOWN,
                ),
                current_turn=turn - 1,
            )
        store.save(memory)
        for _ in range(RECENT_TURNS):
            runtime.advance_memory_turn(pid)
        runtime.end_being_turn(pid)
        runtime.async_event_executor.shutdown(timeout=5)
        runtime.apply_async_results(pid)

        runtime.write_episodes_on_leaving()

        leaving = {p_id: p for k, p_id, p in recorder.events if k == TraceEventKind.EPISODE_WRITING}[int(pid.value)]
        assert (leaving["outcome"], leaving["event_count"]) == ("written", RECENT_TURNS - 10)
        awaited = store.get(being_id).awaited_backstory
        assert leaving["awaited_until_turn"] == (awaited.until_turn if awaited is not None else None)

    def test_leaving_with_a_skip_reason_records_it_without_writing(self) -> None:
        """離れるときに飛ばす理由を渡すと、出来事が残っていても書かず、プレイヤーごとにその理由を残す。"""
        runtime, recorder = _runtime()
        first = runtime.get_player_ids()[0]

        _observe(runtime, first, "火がついた。", 1)
        runtime.write_episodes_on_leaving(skip_reason="llm_unusable")

        assert runtime._being_episode_store.list_by_being(_being_of(runtime, first)) == ()
        writes = [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_WRITING]
        assert len(writes) == len(runtime.get_player_ids())
        assert {(p["trigger"], p["outcome"], p["skip_reason"]) for p in writes} == {
            ("leaving", "skipped", "llm_unusable")
        }
