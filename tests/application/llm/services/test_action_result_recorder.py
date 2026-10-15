"""ActionResultRecorder (U1): append → chunk → promotion を escape baseline 順序・
error isolation で束ねる共有サービスの単体テスト。"""

import inspect
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.action_result_recorder import (
    ActionResultRecorder,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

TEST_BEING_ID = BeingId("being_w1_p1")


class _StoreSpy:
    def __init__(self, events):
        self._events = events
        self.last_kwargs = None

    def append(self, player_id, **kwargs):
        self._events.append("append")
        self.last_kwargs = kwargs


class _ChunkSpy:
    def __init__(self, events, *, raises=False):
        self._events = events
        self._raises = raises
        self.calls = []

    def after_action_recorded(self, player_id, being_id):
        if self._raises:
            raise RuntimeError("chunk boom")
        self._events.append("chunk")
        self.calls.append((player_id, being_id))


class _Stack:
    def __init__(self, chunk):
        self.chunk_coordinator = chunk


def _recorder(events):
    return ActionResultRecorder(_StoreSpy(events))


class TestActionResultRecorder:
    """append + chunk の束ね挙動 (escape baseline)。"""

    def test_records_only_append_when_episodic_stack(self) -> None:
        """episodic_stack=None なら append だけ (記憶 hook skip)。"""
        events: list[str] = []
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", game_time_label=None, episodic_stack=None
        )
        assert events == ["append"]

    def test_hook_order_append_then_chunk(self) -> None:
        """順序は append → chunk。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events))
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", game_time_label=None, episodic_stack=stack, being_id=TEST_BEING_ID
        )
        assert events == ["append", "chunk"]
        assert stack.chunk_coordinator.calls == [(PlayerId(1), TEST_BEING_ID)]

    def test_chunk_exception_is_isolated(self) -> None:
        """chunk が例外でも append 済みで、record は raise しない。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events, raises=True))
        # 例外を伝播しない
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", game_time_label=None, episodic_stack=stack, being_id=TEST_BEING_ID
        )
        # append は済み、chunk は記録されず (raise)
        assert events == ["append"]

    def test_subjective_fields_passed_through_store(self) -> None:
        """intention/emotion_hint を store.append に通す口がある (U2 配線用)。"""
        store = _StoreSpy([])
        ActionResultRecorder(store).record(
            PlayerId(1),
            action_summary="a",
            result_summary="r", game_time_label=None,
            occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            tool_name="t",
            intention="目的Y",
            emotion_hint="curiosity",
            episodic_stack=None,
        )
        assert store.last_kwargs["intention"] == "目的Y"
        assert store.last_kwargs["emotion_hint"] == "curiosity"

    def test_game_time_label_is_required_and_passed_through(self) -> None:
        """記録境界は世界時刻の明示を必須とし、行動結果へそのまま焼き込む。"""
        parameter = inspect.signature(ActionResultRecorder.record).parameters[
            "game_time_label"
        ]
        assert parameter.default is inspect.Parameter.empty
        store = _StoreSpy([])
        recorder = ActionResultRecorder(store)

        recorder.record(
            PlayerId(1),
            action_summary="a",
            result_summary="r",
            game_time_label="Day 2 朝 6:00",
        )

        assert store.last_kwargs["game_time_label"] == "Day 2 朝 6:00"
        with pytest.raises(TypeError, match="game_time_label"):
            recorder.record(  # type: ignore[call-arg]
                PlayerId(1), action_summary="a", result_summary="r"
            )

    def test_None_store_raises(self) -> None:
        """store が None なら TypeError。"""
        with pytest.raises(TypeError, match="action_result_store must not be None"):
            ActionResultRecorder(None)  # type: ignore[arg-type]

