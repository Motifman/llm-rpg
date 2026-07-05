"""ActionResultRecorder (U1): append → chunk → promotion を escape baseline 順序・
error isolation で束ねる共有サービスの単体テスト。"""

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.action_result_recorder import (
    ActionResultRecorder,
)
from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContextLedger,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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

    def after_action_recorded(self, player_id):
        if self._raises:
            raise RuntimeError("chunk boom")
        self._events.append("chunk")
        self.calls.append(player_id)


class _PromotionSpy:
    def __init__(self, events, *, raises=False):
        self._events = events
        self._raises = raises
        self.calls = []

    def on_after_tool_turn(self, player_id_value):
        if self._raises:
            raise RuntimeError("promotion boom")
        self._events.append("promotion")
        self.calls.append(player_id_value)


class _Stack:
    def __init__(self, chunk, promotion):
        self.chunk_coordinator = chunk
        self.episodic_semantic_promotion = promotion


def _recorder(events):
    return ActionResultRecorder(_StoreSpy(events))


class TestActionResultRecorder:
    """append + chunk + promotion の束ね挙動 (escape baseline)。"""

    def test_records_only_append_when_no_episodic_stack(self) -> None:
        """episodic_stack=None なら append だけ (記憶 hook skip)。"""
        events: list[str] = []
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=None
        )
        assert events == ["append"]

    def test_hook_order_append_then_chunk_then_promotion(self) -> None:
        """順序は append → chunk → promotion。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events), _PromotionSpy(events))
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=stack
        )
        assert events == ["append", "chunk", "promotion"]
        assert stack.chunk_coordinator.calls == [PlayerId(1)]
        assert stack.episodic_semantic_promotion.calls == [1]

    def test_promotion_skipped_when_none(self) -> None:
        """promotion が None なら chunk まで。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events), None)
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=stack
        )
        assert events == ["append", "chunk"]

    def test_chunk_exception_is_isolated(self) -> None:
        """chunk が例外でも append 済み・promotion は走り・record は raise しない。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events, raises=True), _PromotionSpy(events))
        # 例外を伝播しない
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=stack
        )
        # append は済み、chunk は記録されず (raise)、promotion は独立に走る
        assert events == ["append", "promotion"]

    def test_promotion_exception_is_isolated(self) -> None:
        """promotion が例外でも append/chunk 済み・record は raise しない。"""
        events: list[str] = []
        stack = _Stack(_ChunkSpy(events), _PromotionSpy(events, raises=True))
        ActionResultRecorder(_StoreSpy(events)).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=stack
        )
        assert events == ["append", "chunk"]

    def test_subjective_fields_passed_through_to_store(self) -> None:
        """expected_result/intention/emotion_hint を store.append に通す口がある (U2 配線用)。"""
        store = _StoreSpy([])
        ActionResultRecorder(store).record(
            PlayerId(1),
            action_summary="a",
            result_summary="r",
            occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            tool_name="t",
            expected_result="予測X",
            intention="目的Y",
            emotion_hint="curiosity",
            episodic_stack=None,
        )
        assert store.last_kwargs["expected_result"] == "予測X"
        assert store.last_kwargs["intention"] == "目的Y"
        assert store.last_kwargs["emotion_hint"] == "curiosity"

    def test_none_store_raises(self) -> None:
        """store が None なら TypeError。"""
        with pytest.raises(TypeError, match="action_result_store must not be None"):
            ActionResultRecorder(None)  # type: ignore[arg-type]


class TestPredictionContextIdConsumption:
    """U1: prediction_context_ledger からの consume → store.append への焼き込み。"""

    def test_ledger_未注入なら_prediction_context_id_は常に_None(self) -> None:
        store = _StoreSpy([])
        ActionResultRecorder(store).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=None
        )
        assert store.last_kwargs["prediction_context_id"] is None

    def test_pending_id_が_consume_されて_store_に渡る(self) -> None:
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        store = _StoreSpy([])
        ActionResultRecorder(store, prediction_context_ledger=ledger).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=None
        )
        assert store.last_kwargs["prediction_context_id"] == issued.prediction_context_id
        # consume 済みなので ledger 側からは消えている
        assert ledger.peek(PlayerId(1)) is None

    def test_pending_id_が無ければ_None_が渡る(self) -> None:
        """no-tool ターンの反対 (record だけ呼ばれて build を経ていない) でも壊れない。"""
        ledger = PredictionContextLedger()
        store = _StoreSpy([])
        ActionResultRecorder(store, prediction_context_ledger=ledger).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=None
        )
        assert store.last_kwargs["prediction_context_id"] is None

    def test_他プレイヤーの_pending_id_は消費されない(self) -> None:
        """player をまたいだ混線防止。"""
        ledger = PredictionContextLedger()
        issued_p2 = ledger.issue(PlayerId(2))
        store = _StoreSpy([])
        ActionResultRecorder(store, prediction_context_ledger=ledger).record(
            PlayerId(1), action_summary="a", result_summary="r", episodic_stack=None
        )
        assert store.last_kwargs["prediction_context_id"] is None
        assert ledger.peek(PlayerId(2)).prediction_context_id == (
            issued_p2.prediction_context_id
        )

    def test_不正な_ledger_型は_TypeError(self) -> None:
        with pytest.raises(TypeError, match="prediction_context_ledger"):
            ActionResultRecorder(
                _StoreSpy([]), prediction_context_ledger=object()  # type: ignore[arg-type]
            )
