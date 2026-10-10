"""create_world_runtime の世界で、1 体の処理の例外が実験設定の方針どおりに取りやめられるか止まるかを保証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from tests.support.trace_recorders import CollectingTraceRecorder

_SCENARIO = Path("data/scenarios/survival_island_v2_short.json")


def _runtime(policy: str) -> Any:
    config = ResolvedLlmRuntimeConfig.from_mapping(values={"WORLD_TICK_FAILURE_POLICY": policy})
    return create_world_runtime(_SCENARIO, config=config)


def _break_first_monster(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """最初に処理されるモンスター 1 体だけ例外を出すようにし、処理を試みた ID を返す。"""
    attempted: list[int] = []
    original = SpotMonsterBehaviorTickService._tick_loaded_monsters

    def tick_or_fail(self: Any, current_tick: Any, **kwargs: Any) -> Any:
        monster_id = kwargs["monster_ids"][0].value
        attempted.append(monster_id)
        if len(attempted) == 1:
            raise RuntimeError("monster brain exploded")
        return original(self, current_tick, **kwargs)

    monkeypatch.setattr(SpotMonsterBehaviorTickService, "_tick_loaded_monsters", tick_or_fail)
    return attempted


class TestIsolateWorld:
    """isolate の世界では、例外を出した 1 体だけを取りやめて tick を進めること。"""

    def test_one_monster_failure_does_not_stop_the_tick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """isolate でモンスター 1 体の行動が例外を出しても tick は進み、残りのモンスターも行動し、trace と件数にその 1 体だけが出る。"""
        runtime = _runtime("isolate")
        recorder = CollectingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        attempted = _break_first_monster(monkeypatch)
        before = runtime.current_tick()

        runtime.advance_tick()

        assert runtime.current_tick() == before + 1
        assert len(attempted) >= 2
        failures = recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
        assert [(e.payload["stage"], e.payload["target_kind"], e.payload["target_id"]) for e in failures] == [
            ("monster_behavior", "monster", attempted[0])
        ]
        assert runtime.world_tick_failure_counts() == {"monster_behavior": 1}

    def test_without_trace_recorder_the_failure_stops_the_tick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """isolate でも trace の記録先が無ければ、取りやめを黙って続けず例外で止める。"""
        runtime = _runtime("isolate")
        _break_first_monster(monkeypatch)

        with pytest.raises(Exception, match="monster brain exploded"):
            runtime.advance_tick()


class TestFailFastWorld:
    """fail_fast の世界では、1 体の例外で tick を止めること。"""

    def test_one_monster_failure_stops_the_tick_after_recording(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fail_fast でモンスター 1 体の行動が例外を出すと、trace に残したうえで advance_tick が例外を投げ、残りのモンスターは行動しない。"""
        runtime = _runtime("fail_fast")
        recorder = CollectingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        attempted = _break_first_monster(monkeypatch)

        with pytest.raises(Exception, match="monster brain exploded"):
            runtime.advance_tick()

        assert len(attempted) == 1
        assert [e.payload["stage"] for e in recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)] == [
            "monster_behavior"
        ]


_STAGES_WITH_PER_UNIT_ISOLATION = (
    "travel",
    "scenario_event",
    "reactive_object_state",
    "sync_action_resolver",
    "monster_spawn",
    "monster_behavior",
    "trade_offer_expiry",
    "market_order_expiry",
    "player_outcome_rule",
    "death_grace",
)


class TestEveryStageSharesTheRuntimeIsolator:
    """create_world_runtime が、1 体ずつ取りやめる段すべてに runtime と同じ部品を渡していること。"""

    @pytest.mark.parametrize("stage_name", _STAGES_WITH_PER_UNIT_ISOLATION)
    def test_stage_uses_the_runtime_isolator(self, stage_name: str) -> None:
        """段が runtime の部品と別の部品 (既定の fail_fast) を持っていると、isolate の run でも 1 体の例外で段ごと取りやめになるので、同じ部品であることを見る。"""
        runtime = create_world_runtime(Path("data/scenarios/mine_village_v1.json"))
        stage = getattr(runtime._simulation_service, f"_{stage_name}_stage")
        # モンスター行動は run を tick へ橋渡しする薄い入れ物に包まれている。
        holder = getattr(stage, "_service", stage)

        assert holder._failure_isolator is runtime.world_tick_failure_isolator


class TestFollowUpFailureInTheRuntime:
    """runtime が tick の後に回す後処理の失敗を、tick を止めずに trace へ残すこと。"""

    def test_public_sns_retry_failure_is_recorded_and_the_tick_completes(self) -> None:
        """isolate で公開 SNS の通知の再送が例外を出しても advance_tick は終わり、public_sns.retry_notifications として続けた失敗が残る。"""
        from unittest.mock import MagicMock

        runtime = _runtime("isolate")
        recorder = CollectingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        broken_sns = MagicMock()
        broken_sns.retry_pending_notifications.side_effect = RuntimeError("outbox locked")
        runtime._public_sns_command_service = broken_sns
        before = runtime.current_tick()

        runtime.advance_tick()

        assert runtime.current_tick() == before + 1
        failures = recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
        assert [(e.payload["stage"], e.payload["continued"]) for e in failures] == [
            ("public_sns.retry_notifications", True)
        ]
