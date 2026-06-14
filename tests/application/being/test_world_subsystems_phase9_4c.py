"""Phase 9-4c codec の単体テスト (sliding_window / obs_buffer / action_result)。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ActionResultStoreSubsystemCodec,
    ObservationBufferSubsystemCodec,
    SlidingWindowMemorySubsystemCodec,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _obs_entry(prose: str = "saw a wolf") -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_NOW,
        output=ObservationOutput(
            prose=prose,
            structured={"event_kind": "encounter"},
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        ),
        game_time_label="Day 1 12:00",
    )


def _action_entry(action: str = "walk") -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=_NOW,
        action_summary=f"{action}_summary",
        result_summary="ok",
        success=True,
        tool_name=action,
        game_time_label="Day 1",
        occurred_tick=42,
    )


class TestSlidingWindowCodec:
    def test_capture_restore_round_trip(self) -> None:
        src = DefaultSlidingWindowMemory()
        src.append(PlayerId(1), _obs_entry("first"))
        src.append(PlayerId(1), _obs_entry("second"))
        src.append(PlayerId(2), _obs_entry("p2 only"))
        src_runtime = SimpleNamespace(_sliding_window=src)
        captured = SlidingWindowMemorySubsystemCodec().capture(src_runtime)
        assert len(captured["entries"]) == 2

        dst = DefaultSlidingWindowMemory()
        dst.append(PlayerId(99), _obs_entry("stale"))  # 復元で消える
        dst_runtime = SimpleNamespace(_sliding_window=dst)
        SlidingWindowMemorySubsystemCodec().restore(dst_runtime, captured)

        assert PlayerId(99).value not in dst._store
        p1 = dst.get_recent(PlayerId(1), limit=10)
        assert [e.output.prose for e in p1] == ["first", "second"]

    def test_sliding_window_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_sliding_window=None)
        captured = SlidingWindowMemorySubsystemCodec().capture(runtime)
        assert captured["entries"] == []
        SlidingWindowMemorySubsystemCodec().restore(runtime, captured)  # no error


class TestObservationBufferCodec:
    def test_capture_restore_round_trip(self) -> None:
        src = DefaultObservationContextBuffer()
        src.append(PlayerId(1), _obs_entry("pending obs"))
        src_runtime = SimpleNamespace(_obs_buffer=src)
        captured = ObservationBufferSubsystemCodec().capture(src_runtime)

        dst = DefaultObservationContextBuffer()
        dst_runtime = SimpleNamespace(_obs_buffer=dst)
        ObservationBufferSubsystemCodec().restore(dst_runtime, captured)
        observations = dst.get_observations(PlayerId(1))
        assert len(observations) == 1
        assert observations[0].output.prose == "pending obs"

    def test_obs_buffer_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_obs_buffer=None)
        captured = ObservationBufferSubsystemCodec().capture(runtime)
        assert captured["entries"] == []


class TestActionResultStoreCodec:
    def test_capture_restore_round_trip(self) -> None:
        src = DefaultActionResultStore()
        # DefaultActionResultStore.append のシグネチャは複雑なので直接 _store
        # に詰める (= test 用)。実本番では append 経由で乗る。
        src._store[1] = [_action_entry("walk"), _action_entry("attack")]
        src_runtime = SimpleNamespace(_action_result_store=src)
        captured = ActionResultStoreSubsystemCodec().capture(src_runtime)
        assert len(captured["entries"][0]["entries"]) == 2

        dst = DefaultActionResultStore()
        dst_runtime = SimpleNamespace(_action_result_store=dst)
        ActionResultStoreSubsystemCodec().restore(dst_runtime, captured)
        results = dst.get_recent(PlayerId(1), limit=10)
        assert [e.action_summary for e in results] == [
            "walk_summary",
            "attack_summary",
        ]
        assert results[0].occurred_tick == 42

    def test_action_result_store_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_action_result_store=None)
        captured = ActionResultStoreSubsystemCodec().capture(runtime)
        assert captured["entries"] == []


class TestUnsupportedSchemaVersion:
    @pytest.mark.parametrize(
        "codec_cls",
        [
            SlidingWindowMemorySubsystemCodec,
            ObservationBufferSubsystemCodec,
            ActionResultStoreSubsystemCodec,
        ],
    )
    def test_未サポート_schema_version_は_例外(self, codec_cls) -> None:
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
