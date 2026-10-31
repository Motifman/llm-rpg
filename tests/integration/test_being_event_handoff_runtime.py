"""本番の runtime で、Being の保存先が保存するときにイベントを配送器に渡し、ハンドラが trace に残すことを保証する (design_decisions D1837 の 6、D1824-11)。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoKind
from ai_rpg_world.being.domain.short_term_memory import Backstory
from ai_rpg_world.domain.being.value_object.being_id import BeingId
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
    """create_world_runtime が組んだ Being の保存先と配送器が、保存のたびにイベントをハンドラまで届けることを保証する。"""

    def test_oldest_turns_dropped_reaches_the_trace(self) -> None:
        """短期記憶の範囲が上限に届いて待たずに古いターンを外したことは、保存すると being_short_term_memory_fold_forced として trace に残る。"""
        runtime, recorder, being_id = _runtime()
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        memory.perceive(_seen(), current_turn=0)
        memory.end_turn(turn=40)

        store.save(memory)

        (payload,) = recorder.payloads(TraceEventKind.BEING_SHORT_TERM_MEMORY_FOLD_FORCED)
        assert (payload["being_id"], payload["turn"], payload["until_turn"], payload["dropped_count"]) == (
            being_id.value,
            40,
            10,
            1,
        )

    def test_memo_book_with_events_is_saved_through_the_dispatcher(self) -> None:
        """ハンドラの無いメモ帳のイベントも配送器を通り、保存したメモ帳は取り出せる。"""
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
        """思い出したエピソードのイベントも配送器を通り、保存したエピソードは思い出した回数を持って取り出せる。"""
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
    """本番の runtime で、短期記憶の範囲が埋まるといきさつが裏で作られ、その Being のターンの始めに入ることを保証する (design_decisions D1824-12)。"""

    @staticmethod
    def _fill_range(runtime, being_id) -> None:
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        for turn in range(0, 20):
            memory.perceive(_seen(), current_turn=turn)
        memory.end_turn(turn=20)
        store.save(memory)

    def test_backstory_for_the_filled_range_is_added_at_the_turn_entry(self) -> None:
        """範囲が埋まった短期記憶を保存すると、裏で作ったいきさつ (スタブ) が、その Being の結果を反映したときに入り、ターン 10 までの出来事が外れ、being_backstory_written が残る。"""
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._fill_range(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert ([b.until_turn for b in memory.backstories], memory.recent_from, memory.awaited_backstory) == (
            [10],
            11,
            None,
        )
        assert memory.backstories[0].flow.startswith("(スタブ) ")
        (payload,) = recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN)
        assert (payload["being_id"], payload["until_turn"], payload["dropped_count"]) == (being_id.value, 10, 10)

    def test_stale_backstory_is_refused_without_stopping_the_turn_entry(self) -> None:
        """範囲が埋まって書いたいきさつと、遅れを知らせて書き直した同じ範囲のいきさつが両方届くと、1 つ目が入り、2 つ目は短期記憶が断る。断ったことは async_event_delivery_failed (application_failed) に残り、結果を反映しても例外は投げない (design_decisions D1824-15、D1824-17)。"""
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._fill_range(runtime, being_id)
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        memory.end_turn(turn=30)
        store.save(memory)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        assert [b.until_turn for b in store.get(being_id).backstories] == [10]
        (failure,) = recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)
        assert (failure["reason"], failure["event_type"], failure["handler"], failure["error_type"]) == (
            "application_failed",
            "ShortTermMemoryBackstoryOverdueEvent",
            "WriteBackstoryHandler",
            "ShortTermMemoryStaleBackstoryException",
        )
        assert len(recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN)) == 1

    def test_backstory_is_not_added_before_the_turn_entry(self) -> None:
        """裏でいきさつができても、その Being の結果を反映するまでは短期記憶は変わらない (書くのはターンを進めるスレッドだけ)。"""
        runtime, _, being_id = _runtime()
        self._fill_range(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        memory = runtime._being_short_term_memory_store.get(being_id)

        assert (memory.backstories, memory.recent_from) == ((), 1)
        runtime.shutdown_async_events()

    def test_pending_backstory_is_added_when_async_events_shut_down(self) -> None:
        """ターンの始めを待たずに run を終えても、終える処理 (shutdown_async_events) が、できていたいきさつを入れる。"""
        runtime, recorder, being_id = _runtime()
        self._fill_range(runtime, being_id)

        runtime.shutdown_async_events()

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert ([b.until_turn for b in memory.backstories], memory.awaited_backstory) == ([10], None)
        assert len(recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN)) == 1

    def test_failed_writing_reaches_the_trace_and_keeps_waiting(self, monkeypatch) -> None:
        """LLM の応答が崩れていきさつを書けなければ async_event_delivery_failed が残り、いきさつは入らず、短期記憶は待ち続ける (遅れたら知らせ、書き直される)。"""
        monkeypatch.setattr(
            "ai_rpg_world.application.llm.services.stub_backstory_completion.stub_backstory_completion",
            lambda messages: "JSON ではない応答",
        )
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._fill_range(runtime, being_id)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        memory = runtime._being_short_term_memory_store.get(being_id)
        assert (memory.backstories, memory.awaited_backstory is not None) == ((), True)
        (failure,) = recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)
        assert (failure["reason"], failure["handler"]) == ("handler_failed", "WriteBackstoryHandler")
        assert recorder.payloads(TraceEventKind.BEING_BACKSTORY_WRITTEN) == []

    def test_being_without_a_player_is_reported_as_prepare_failed(self) -> None:
        """どのプレイヤーにも結びつかない Being の範囲が埋まると、いきさつとエピソードを書く 2 つのハンドラが名前と人格の文を引けず、それぞれ prepare_failed として async_event_delivery_failed に残る。裏の仕事は受け付けない。"""
        runtime, recorder, _ = _runtime()
        stranger = BeingId("being_nobody")

        self._fill_range(runtime, stranger)

        failures = recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)
        assert sorted((f["reason"], f["handler"], f["error_type"]) for f in failures) == [
            ("prepare_failed", "WriteBackstoryHandler", "LookupError"),
            ("prepare_failed", "WriteEpisodesHandler", "LookupError"),
        ]
        runtime.shutdown_async_events()
        assert runtime._being_short_term_memory_store.get(stranger).backstories == ()


class TestEpisodeWritingInTheRuntime:
    """本番の runtime で、短期記憶の範囲が埋まると、その範囲のエピソードが裏で書かれ、その Being のターンの始めに記憶に加わることを保証する (design_decisions D1824-19)。"""

    @staticmethod
    def _end_turns(runtime, being_id, *, turns: range, end_at: int) -> None:
        store = runtime._being_short_term_memory_store
        memory = store.get(being_id)
        for turn in turns:
            memory.perceive(_seen(), current_turn=turn)
        memory.end_turn(turn=end_at)
        store.save(memory)

    def test_episodes_for_the_filled_range_are_added_at_the_turn_entry(self) -> None:
        """範囲が埋まった短期記憶を保存すると、書いたエピソード (スタブ) が、その Being の結果を反映したときに記憶に加わり、being_episode_written が残る。反映するまでは加わらない。"""
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._end_turns(runtime, being_id, turns=range(0, 20), end_at=20)
        runtime.async_event_executor.shutdown(timeout=5)
        assert runtime._being_episode_store.list_by_being(being_id) == ()

        runtime.apply_async_results(player)

        (episode,) = runtime._being_episode_store.list_by_being(being_id)
        assert (episode.body.startswith("(スタブ) "), episode.written_turn) == (True, 20)
        (payload,) = recorder.payloads(TraceEventKind.BEING_EPISODE_WRITTEN)
        assert (payload["being_id"], payload["handle"], payload["written_turn"]) == (being_id.value, episode.handle, 20)

    def test_overdue_backstory_does_not_write_episodes_again(self) -> None:
        """いきさつが遅れて同じ範囲を書き直しても (書き直したいきさつは古い範囲として断られる)、エピソードは書き直さない。エピソードを書くハンドラの失敗も残らない。"""
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._end_turns(runtime, being_id, turns=range(0, 20), end_at=20)
        self._end_turns(runtime, being_id, turns=range(20, 30), end_at=30)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        assert len(runtime._being_episode_store.list_by_being(being_id)) == 1
        failures = recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)
        assert [(f["event_type"], f["handler"], f["error_type"]) for f in failures] == [
            ("ShortTermMemoryBackstoryOverdueEvent", "WriteBackstoryHandler", "ShortTermMemoryStaleBackstoryException")
        ]

    def test_failed_episode_writing_reaches_the_trace(self, monkeypatch) -> None:
        """LLM の応答が崩れてエピソードを書けなければ、handler_failed として WriteEpisodesHandler の名前で async_event_delivery_failed に残り、記憶には何も加わらない。"""
        monkeypatch.setattr(
            "ai_rpg_world.application.llm.services.stub_episode_writing_completion.StubEpisodeWritingCompletion.complete_episode_writing_json",
            lambda self, messages: "JSON ではない応答",
        )
        runtime, recorder, being_id = _runtime()
        player = runtime.get_player_ids()[0]
        self._end_turns(runtime, being_id, turns=range(0, 20), end_at=20)
        runtime.async_event_executor.shutdown(timeout=5)

        runtime.apply_async_results(player)

        assert runtime._being_episode_store.list_by_being(being_id) == ()
        (failure,) = recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)
        assert (failure["reason"], failure["handler"], failure["event_type"]) == (
            "handler_failed",
            "WriteEpisodesHandler",
            "ShortTermMemoryRangeFilledEvent",
        )
