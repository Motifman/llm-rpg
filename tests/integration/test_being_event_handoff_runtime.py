"""本番の runtime で、Being の保存先が保存するときにイベントを配り手に渡し、受け手が trace に残すことを保証する (design_decisions D1837 の 6、D1824-11)。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoKind
from ai_rpg_world.being.domain.short_term_memory import Backstory
from tests.trace_helpers import RecordingTraceRecorder

_ISLAND = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island_v4_coop.json"


def _runtime():
    runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.for_tests())
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    being_id = runtime._acting_being_for(runtime.get_player_ids()[0]).being_id
    return runtime, recorder, being_id


def _seen() -> Observation:
    return Observation(
        body="鐘が鳴った",
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


class TestBeingEventHandoffInTheRuntime:
    """create_world_runtime が組んだ Being の保存先と配り手が、保存のたびにイベントを受け手まで届けることを保証する。"""

    def test_fold_forced_reaches_the_trace(self) -> None:
        """短期記憶の範囲が上限に届いて待たずに外したことは、保存すると being_short_term_memory_fold_forced として trace に残る。"""
        runtime, recorder, being_id = _runtime()
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        memory.perceive(_seen(), current_turn=0)
        memory.fold(current_turn=40)

        store.save(memory)

        (payload,) = recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_FOLD_FORCED)
        assert (payload["being_id"], payload["turn"], payload["until_turn"], payload["dropped_count"]) == (
            being_id.value,
            40,
            10,
            1,
        )

    def test_discarded_backstory_reaches_the_trace(self) -> None:
        """持っているいきさつと同じ範囲のいきさつは入らず、保存すると being_backstory_discarded として trace に残る。"""
        runtime, recorder, being_id = _runtime()
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        memory.add_backstory(Backstory(flow="浜で流木を拾った", mood="", written_turn=10, until_turn=10))
        memory.add_backstory(Backstory(flow="遅れて届いた", mood="", written_turn=11, until_turn=10))

        store.save(memory)

        (payload,) = recorder.payloads(TraceEventKind.BEING_BACKSTORY_DISCARDED)
        assert (payload["until_turn"], payload["latest_until_turn"]) == (10, 10)

    def test_memo_book_with_events_is_saved_through_the_dispatcher(self) -> None:
        """受け手の無いメモ帳のイベントも配り手を通り、保存したメモ帳は取り出せる。"""
        runtime, _, being_id = _runtime()
        store = runtime._being_memo_store
        book = store.get(being_id)
        book.add(
            memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
            kind=MemoKind.TODO,
            text="火を起こす",
            provenance=None,
            turn=1,
            environment_name="島",
        )

        store.save(book)

        assert ([m.text for m in store.get(being_id).memos], book.get_events()) == (["火を起こす"], [])

    def test_episode_with_events_is_saved_through_the_dispatcher(self) -> None:
        """思い出したエピソードのイベントも配り手を通り、保存したエピソードは思い出した回数を持って取り出せる。"""
        runtime, _, being_id = _runtime()
        store = runtime._being_episode_store
        store.add(
            Episode.write(
                being_id=being_id,
                episode_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
                environment_name="島",
                written_turn=1,
                index=EpisodeIndex(summary="火を起こした", recall_when="火の話"),
                body="流木を集めた。",
                taken_handles=set(),
            )
        )
        episode = store.list_by_being(being_id)[0]
        episode.recall(turn=2)

        store.save(episode)

        assert (store.list_by_being(being_id)[0].recall_count, episode.get_events()) == (1, [])


class TestBackstoryWritingInTheRuntime:
    """本番の runtime で、短期記憶が頼んだいきさつが裏で作られ、その Being のターンの始めに入ることを保証する (design_decisions D1824-12)。"""

    @staticmethod
    def _request(runtime, being_id) -> None:
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        for turn in range(0, 20):
            memory.perceive(_seen(), current_turn=turn)
        memory.fold(current_turn=20)
        store.save(memory)

    def test_requested_backstory_is_added_at_the_turn_entry(self) -> None:
        """いきさつを頼んで保存すると、裏で作ったいきさつ (スタブ) が、その Being の結果を反映したときに入り、ターン 10 までの出来事が外れ、being_backstory_written が残る。"""
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._request(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert ([b.until_turn for b in memory.backstories], memory.recent_from, memory.request) == ([10], 11, None)
        assert memory.backstories[0].flow.startswith("(スタブ) ")
        (payload,) = recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN)
        assert (payload["being_id"], payload["until_turn"]) == (being_id.value, 10)

    def test_backstory_is_not_added_before_the_turn_entry(self) -> None:
        """裏でいきさつができても、その Being の結果を反映するまでは短期記憶は変わらない (書くのはターンを進めるスレッドだけ)。"""
        runtime, _, being_id = _runtime()
        self._request(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        memory = runtime._being_short_term_memory_store.get(being_id)

        assert (memory.backstories, memory.recent_from) == ((), 1)
        runtime.shutdown_async_events()

    def test_pending_backstory_is_added_when_async_events_shut_down(self) -> None:
        """ターンの始めを待たずに run を終えても、終える処理 (shutdown_async_events) が、できていたいきさつを入れる。"""
        runtime, recorder, being_id = _runtime()
        self._request(runtime, being_id)

        runtime.shutdown_async_events()

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert ([b.until_turn for b in memory.backstories], memory.request) == ([10], None)
        assert len(recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN)) == 1

    def test_failed_writing_reaches_the_trace_and_keeps_the_request(self, monkeypatch) -> None:
        """LLM の応答が崩れていきさつを書けなければ async_event_delivery_failed が残り、いきさつは入らず、頼みごとが残る (短期記憶が頼み直す)。"""
        monkeypatch.setattr(
            "ai_rpg_world.application.llm.services.stub_backstory_completion.stub_backstory_completion",
            lambda messages: "JSON ではない応答",
        )
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._request(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert (memory.backstories, memory.request is not None) == ((), True)
        assert len(recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)) == 1
        assert recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN) == []
