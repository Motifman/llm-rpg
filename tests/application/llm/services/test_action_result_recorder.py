"""ActionResultRecorder (U1): 行動結果を store に積む共有サービスの単体テスト。"""

import inspect
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.action_result_recorder import (
    ActionResultRecorder,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StoreSpy:
    def __init__(self, events):
        self._events = events
        self.last_kwargs = None

    def append(self, player_id, **kwargs):
        self._events.append("append")
        self.last_kwargs = kwargs


class TestActionResultRecorder:
    """行動結果を store に積む挙動。"""

    def test_records_only_append(self) -> None:
        """record は store に 1 件 append するだけで、ほかの hook を回さない。"""
        events: list[str] = []
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", game_time_label=None
        )
        assert events == ["append"]

    def test_subjective_fields_passed_through_store(self) -> None:
        """独白 inner_thought を store.append に通す口がある (U2 配線用)。"""
        store = _StoreSpy([])
        ActionResultRecorder(store).record(
            PlayerId(1),
            action_summary="a",
            result_summary="r", game_time_label=None,
            occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            tool_name="t",
            inner_thought="独白Y",
        )
        assert store.last_kwargs["inner_thought"] == "独白Y"

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

