"""ゲームの runtime が、確定した予期の受け取る側を配り手に登録し、記憶の store と同じものに書く配線を保証する (#1443)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_rpg_world.application.being.expectation.belief_material import (
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.being.expectation.chunk_note import (
    ExpectationChunkNoteReceiver,
)
from ai_rpg_world.application.being.expectation.recall_credit import (
    ExpectationRecallCreditReceiver,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.application.being.expectation.support import RecordingTraceRecorder
from tests.runtime_config_helpers import episodic_config

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "forbidden_library_demo.json"
)


def _runtime(**overrides: Any) -> Any:
    return create_world_runtime(_SCENARIO, config=episodic_config(**overrides))


def _receiver_types(runtime: Any) -> list[type]:
    return [type(r) for r in runtime._expectation_dispatcher._receivers]


def _being(runtime: Any) -> BeingId:
    acting = runtime._acting_being_for(PlayerId(1))
    assert acting is not None
    return acting.being_id


def _save_settled_miss(runtime: Any, being: BeingId) -> None:
    expectation = Expectation(
        expectation_id=ExpectationId("exp-1"),
        holder=being,
        content="書架の奥に地図がある",
        origin=ExpectationOrigin.WITH_ACTION,
        likelihood=Likelihood.ALMOST_CERTAIN,
        formed_at_turn=1,
        expires_at_turn=10,
        beliefs_in_mind=("belief-shelf",),
        episodes_in_mind=("ep-shelf",),
    )
    expectation.record(Check(turn=2, verdict=CheckVerdict.MISS))
    settled = expectation.record(Check(turn=3, verdict=CheckVerdict.MISS))
    assert settled is not None
    runtime._expectation_store.save(expectation, [settled])


class TestReceiversRegistered:
    """記憶の機能が有効なときだけ、その記憶へ書く受け取る側が登録される挙動を保証する。"""

    def test_all_receivers_registered_when_memory_features_are_on(self) -> None:
        """信念の証拠・想起の信用割り当て・エピソードが有効なら、3 つの受け取る側がこの順で登録される。"""
        runtime = _runtime(
            belief_evidence_enabled=True,
            recall_hit_boost_enabled=True,
            prediction_context_id_enabled=True,
            episodic_reinterpretation_enabled=True,
            error_driven_reinterpretation_enabled=True,
        )

        assert _receiver_types(runtime) == [
            ExpectationBeliefMaterialReceiver,
            ExpectationRecallCreditReceiver,
            ExpectationChunkNoteReceiver,
        ]

    def test_only_chunk_note_when_belief_and_recall_features_are_off(self) -> None:
        """信念の証拠と想起の信用割り当てが無効なら、エピソードへ渡す受け取る側だけが登録される。"""
        runtime = _runtime()

        assert _receiver_types(runtime) == [ExpectationChunkNoteReceiver]

    def test_receivers_write_to_the_stack_stores(self) -> None:
        """受け取る側が書く先は、snapshot が拾う記憶の store と同じものである。"""
        runtime = _runtime(
            belief_evidence_enabled=True,
            recall_hit_boost_enabled=True,
            prediction_context_id_enabled=True,
            episodic_reinterpretation_enabled=True,
            error_driven_reinterpretation_enabled=True,
        )
        stack = runtime._episodic_stack
        belief, recall, chunk = runtime._expectation_dispatcher._receivers

        assert belief._buffer_store is stack.belief_evidence_buffer_store
        assert recall._success_store is stack.recall_success_store
        assert chunk._sink is stack.chunk_coordinator


class TestRecallBufferNeedsErrorDrivenReinterpretation:
    """外れを想起に書き添えるのは、誤差駆動の再解釈が有効で想起の記録があるときだけである挙動を保証する。"""

    def _stack(self, recall_buffer: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            belief_evidence_buffer_store=None,
            recall_success_store=None,
            recall_buffer_store=recall_buffer,
            chunk_coordinator=_Sink(),
        )

    def test_recall_buffer_is_handed_when_error_driven_is_on(self) -> None:
        """誤差駆動の再解釈が有効なら、想起の記録を持つ受け取る側が登録される。"""
        from types import SimpleNamespace

        from ai_rpg_world.application.world_runtime.world_runtime import (
            _expectation_event_receivers,
        )

        buffer = InMemoryEpisodicRecallBufferStore()
        runtime = SimpleNamespace(_episodic_stack=self._stack(buffer), _trace_recorder=None)
        config = episodic_config(error_driven_reinterpretation_enabled=True)

        recall, _ = _expectation_event_receivers(runtime, config)

        assert isinstance(recall, ExpectationRecallCreditReceiver)
        assert recall._recall_buffer_store is buffer

    def test_recall_buffer_is_not_handed_when_error_driven_is_off(self) -> None:
        """誤差駆動の再解釈が無効なら、想起の記録があっても書き添える受け取る側は登録されない。"""
        from types import SimpleNamespace

        from ai_rpg_world.application.world_runtime.world_runtime import (
            _expectation_event_receivers,
        )

        runtime = SimpleNamespace(
            _episodic_stack=self._stack(InMemoryEpisodicRecallBufferStore()),
            _trace_recorder=None,
        )

        receivers = _expectation_event_receivers(runtime, episodic_config())

        assert [type(r) for r in receivers] == [ExpectationChunkNoteReceiver]


class _Sink:
    def note_settled_miss(self, being_id: Any, missed: Any) -> bool:
        return True


class TestDeliveredToMemory:
    """runtime の配り手で確定の出来事を配ると、信念の材料になり、配り直しても 1 回分のままである挙動を保証する。"""

    def test_settled_miss_becomes_one_material_even_when_redelivered(self) -> None:
        """外れの確定を配ると証拠が 1 件積まれ、同じ出来事が未配信に戻って配り直されても 1 件のまま。"""
        runtime = _runtime(belief_evidence_enabled=True)
        recorder = RecordingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        being = _being(runtime)
        _save_settled_miss(runtime, being)
        undelivered = runtime._expectation_store.list_undelivered_by_being(being)

        runtime.redeliver_expectation_events([being])
        runtime._expectation_store.replace_all_by_being(
            being,
            expectations=runtime._expectation_store.list_all_by_being(being),
            undelivered_events=undelivered,
            turn=3,
        )
        runtime.redeliver_expectation_events([being])

        buffer = runtime._episodic_stack.belief_evidence_buffer_store
        (material,) = buffer.list_all_by_being(being)
        assert material.in_context_belief_ids == ("belief-shelf",)
        assert material.salience == "high"
        results = [
            t["result"]
            for t in recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL)
            if t["receiver"] == "belief_evidence"
        ]
        assert results == ["appended", "already_received"]
