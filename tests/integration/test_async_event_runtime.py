"""共通の非同期配送を、世界の trace とターンの入口へ接続する。"""

from datetime import datetime, timezone
from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.eventing import DomainEvent
from tests.support.trace_recorders import CollectingTraceRecorder


def _runtime(**overrides):
    runtime = create_world_runtime(Path("data/scenarios/survival_island_v3_coop.json"), config=ResolvedLlmRuntimeConfig.for_tests(**overrides))
    recorder = CollectingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    return runtime, recorder


def test_async_handler_failure_reaches_world_trace() -> None:
    """別スレッドの受け手が失敗すると、本人・イベント・理由と例外を世界の trace に残す。"""
    runtime, recorder = _runtime()
    executor = runtime.async_event_executor

    def fail(event: DomainEvent) -> None:
        raise RuntimeError("receiver failed")

    executor.submit(key="being-a", event=DomainEvent(42, datetime.now(timezone.utc)), handler=fail, apply_result=lambda _: None)
    runtime.shutdown_async_events()
    events = recorder.of_kind("async_event_delivery_failed")
    assert len(events) == 1
    assert events[0].payload["recipient_key"] == "being-a"
    assert events[0].payload["event_id"] == 42
    assert events[0].payload["reason"] == "handler_failed"
    assert events[0].payload["error_message"] == "receiver failed"


def test_turn_entry_applies_only_that_beings_results(monkeypatch) -> None:
    """ターンを始めると、その本人の結果だけをプロンプトを作る前に反映する。"""
    from ai_rpg_world.application.llm.services.world_llm_turn import wiring as module

    runtime, _ = _runtime()
    player = runtime.get_player_ids()[0]
    key = runtime._acting_being_for(player).being_id.value
    applied = []
    for recipient in (key, "someone-else"):
        runtime.async_event_executor.submit(key=recipient, event=DomainEvent(1, datetime.now(timezone.utc)), handler=lambda event: event.event_id, apply_result=lambda value, who=recipient: applied.append(who))
    runtime.async_event_executor.shutdown(timeout=2)
    wiring = module.WorldLlmWiring.__new__(module.WorldLlmWiring)
    wiring.runtime = runtime

    def phase_a(wiring, player_id):
        assert applied == [key]
        return "phase-a"

    monkeypatch.setattr(module, "run_phase_a", phase_a)
    assert wiring.run_phase_a(player) == "phase-a"
    runtime.shutdown_async_events()
    assert applied == [key, "someone-else"]


def test_rejections_and_abandoned_work_reach_trace() -> None:
    """件数超過・終了期限の破棄・終了後の拒否を、それぞれの理由付きで trace に残す。"""
    from concurrent.futures import wait
    from threading import Event
    entered, release = Event(), Event()
    runtime, recorder = _runtime(async_event_max_pending=1, async_event_shutdown_timeout_seconds=0)
    executor = runtime.async_event_executor

    def work(event):
        entered.set()
        assert release.wait(5)

    try:
        executor.submit(key="a", event=DomainEvent(1, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
        assert entered.wait(5)
        assert not executor.submit(key="a", event=DomainEvent(2, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
        runtime.shutdown_async_events()
        assert not executor.submit(key="a", event=DomainEvent(3, datetime.now(timezone.utc)), handler=work, apply_result=lambda _: None)
        assert [event.payload["reason"] for event in recorder.of_kind("async_event_delivery_failed")] == ["capacity", "shutdown_timeout", "shutdown"]
    finally:
        release.set()
        wait(tuple(executor._futures), timeout=5)
        runtime.shutdown_async_events()


def test_experiment_waits_and_applies_results_before_snapshot(tmp_path, monkeypatch) -> None:
    """終了の待機で完了した結果を呼び出す側で反映してから snapshot を保存する。"""
    from concurrent.futures import wait
    from threading import Event, get_ident

    from scripts import run_scenario_experiment as runner

    from ai_rpg_world.application.being.experiment_snapshot_session import ExperimentSnapshotSession
    from ai_rpg_world.eventing import async_delivery
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager

    entered, release = Event(), Event()
    owner = get_ident()
    aggregate = {"id": "a", "value": 0}
    runtimes, captures = [], []
    create_session = GameRuntimeManager.create_session
    capture_all = ExperimentSnapshotSession.capture_all

    def apply(value):
        assert get_ident() == owner
        aggregate["value"] = value

    def create(manager, request):
        response = create_session(manager, request)
        runtime = manager._sessions[response.session_id].runtime
        runtimes.append(runtime)

        def work(event):
            entered.set()
            assert release.wait(10)
            return 7

        runtime.async_event_executor.submit(key="a", event=DomainEvent(1, datetime.now(timezone.utc)), handler=work, apply_result=apply)
        assert entered.wait(5)
        return response

    def finish(futures, timeout):
        release.set()
        return wait(futures, timeout=timeout)

    def capture(session, *args, **kwargs):
        assert aggregate["value"] == 7
        captures.append(aggregate["value"])
        return capture_all(session, *args, **kwargs)

    monkeypatch.setattr(GameRuntimeManager, "create_session", create)
    monkeypatch.setattr(async_delivery, "wait", finish)
    monkeypatch.setattr(ExperimentSnapshotSession, "capture_all", capture)
    try:
        runner._drive_scenario(
            run_id="async-snapshot", scenario_path=Path("data/scenarios/survival_island_v3_coop.json"),
            max_world_ticks=1, recorder=CollectingTraceRecorder(), progress=lambda _: None,
            runtime_config=ResolvedLlmRuntimeConfig.for_tests(async_event_shutdown_timeout_seconds=2),
            snapshot_save_dir=tmp_path / "snapshots",
        )
        assert captures == [7]
    finally:
        release.set()
        for runtime in runtimes:
            runtime.shutdown_async_events()


def test_experiment_stops_accepting_work_when_a_tick_raises(monkeypatch) -> None:
    """実験の途中で例外が起きても、非同期の新しい受付を止める。"""
    import pytest
    from scripts import run_scenario_experiment as runner

    from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime

    runtimes = []

    def fail(runtime, dt=1):
        runtimes.append(runtime)
        raise RuntimeError("tick failed")

    monkeypatch.setattr(WorldRuntime, "advance_tick", fail)
    with pytest.raises(RuntimeError, match="tick failed"):
        runner._drive_scenario(
            run_id="async-cleanup", scenario_path=Path("data/scenarios/survival_island_v3_coop.json"),
            max_world_ticks=1, recorder=CollectingTraceRecorder(), progress=lambda _: None,
            runtime_config=ResolvedLlmRuntimeConfig.for_tests(),
        )
    assert len(runtimes) == 1
    assert not runtimes[0].async_event_executor.submit(
        key="a", event=DomainEvent(1, datetime.now(timezone.utc)),
        handler=lambda event: None, apply_result=lambda result: None,
    )
