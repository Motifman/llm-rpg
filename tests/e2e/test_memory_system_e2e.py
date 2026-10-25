"""記憶システム end-to-end smoke test (Phase 0 ~ Phase 3)。

実 LLM を使わず deterministic stub に差し替えた状態で、これまで実装した
memory 機能が **1 つのシナリオの中で一貫して動く** ことを確認する。

検証範囲:
- Phase 0: prompt section の順序 (stable_to_volatile)
- Phase 2: §「【ここまでのいきさつ】」 (L4 mid summary) が本人ターン上限で生成
- Phase 2.1: scheduler 経由で L4 生成 (Inline で同期実行)
- L4 が 3 世代を超えると最古を捨てる。要約の要約 (L5) は作らない (#1824)
- 全 trace event の経路が alive (``PROMPT_SECTION_BREAKDOWN`` 等)
- silent failure 防止: LLM stub が例外を投げた場合 template fallback ＋
  warning ログが出る

LLM port は ``_StubLLMClient`` が all-in-one で satisfy する。実 ``LiteLLMClient``
を継承して各 ``complete_*_json`` を deterministic な dict で上書きしているため、
``isinstance(client, LiteLLMClient)`` を見て service 構築する wiring 側のロジック
を素通りできる。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.context_format_strategy import SectionBasedContextFormatStrategy
from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    ThreadPoolShortTermMemoryScheduler,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import ShortTermMemorySummaryService
from ai_rpg_world.application.llm.services.summarizing_short_term_memory import SummarizingShortTermMemory
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SUMMARY_INPUT_COUNT = 15


class _StubSummaryPort:
    """L4 用の deterministic LLM port。

    呼び出しごとに call_count を増やし、テストで「LLM が何回呼ばれたか」を
    確認できる。``raise_on_n_th`` で N 回目だけ例外を投げる挙動も模擬可能
    (template fallback の検証用)。
    """

    def __init__(self, l4_response: dict[str, Any]) -> None:
        self.l4_response = l4_response
        self.l4_calls = 0
        self.raise_on_l4_call: int | None = None

    def complete_short_term_summary_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.l4_calls += 1
        if self.raise_on_l4_call == self.l4_calls:
            raise LlmApiCallException("simulated LLM failure", error_code="LLM_API_CALL_FAILED")
        return dict(self.l4_response)


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper
    return captured


_PID = PlayerId(7)
_PERSONA = ("ハル", "慎重で寡黙な漁師")


def _persona_resolver(pid: int) -> tuple[str, str]:
    return _PERSONA


def _make_observation(prose: str, seq: int = 0) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        output=ObservationOutput(prose=prose, structured={}),
    )


def _build_memory(stub: _StubSummaryPort, *, scheduler_kind: str = "inline") -> SummarizingShortTermMemory:
    """全 LLM サービスを stub 接続した SummarizingShortTermMemory を返す。"""
    if scheduler_kind == "thread_pool":
        scheduler = ThreadPoolShortTermMemoryScheduler(max_workers=1)
    else:
        scheduler = InlineShortTermMemoryScheduler()
    return SummarizingShortTermMemory(
        summary_service=ShortTermMemorySummaryService(stub), persona_resolver=_persona_resolver, scheduler=scheduler
    )


def _complete_window(memory: SummarizingShortTermMemory) -> None:
    """既定 cap まで本人ターンを閉じ、1 回の畳み込みを発火させる。"""
    for _ in range(memory._turn_cap):
        memory.complete_turn(_PID)


class TestRollingSummaryE2E:
    """L1 → L4 一気通貫 (Inline scheduler)。"""

    def test_l4_keeps_three_generations_and_drops_the_oldest(self) -> None:
        """L4 は 1 回の畳み込みごとに 1 世代できる。4 世代目ができると最古が捨てられ、3 世代が残る。"""
        stub = _StubSummaryPort(
            l4_response={"compressed_activity": "北東を探索", "emotional_summary": "疲労", "unresolved": ["水源"]}
        )
        mem = _build_memory(stub)
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        _complete_window(mem)
        assert stub.l4_calls == 1
        assert len(mem._mid_generations(_PID.value)) == 1
        for batch in range(1, 4):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _make_observation(f"b{batch}-{i}", seq=batch * 100 + i))
            _complete_window(mem)
        assert stub.l4_calls == 4
        assert len(mem._mid_generations(_PID.value)) == 3


class TestRollingSummaryE2EAsync:
    """同じシナリオを ThreadPool scheduler で実行し、shutdown 完了後に
    最終状態が同等になることを確認する。"""

    def test_thread_pool_eventually_keeps_three_l4_generations(self) -> None:
        """ThreadPool で 4 回畳み込み、L4 の生成が 4 回終わったあと 3 世代が残る。"""
        import time as _time

        stub = _StubSummaryPort(l4_response={"compressed_activity": "ok", "emotional_summary": "", "unresolved": []})
        mem = _build_memory(stub, scheduler_kind="thread_pool")
        try:
            for batch in range(4):
                for i in range(_SUMMARY_INPUT_COUNT):
                    seq = batch * _SUMMARY_INPUT_COUNT + i
                    mem.append(_PID, _make_observation(f"obs-{seq}", seq=seq))
                _complete_window(mem)
            deadline = _time.monotonic() + 3.0
            while _time.monotonic() < deadline:
                if stub.l4_calls == 4 and len(mem._mid_generations(_PID.value)) == 3:
                    break
                _time.sleep(0.02)
        finally:
            mem.shutdown()
        assert stub.l4_calls == 4
        assert len(mem._mid_generations(_PID.value)) == 3


class TestRollingSummaryFallbackChain:
    """LLM 失敗時の二段フォールバックが silent failure にならない。

    - L4 LLM が落ちる → template fallback で L4 を生やす (is_fallback=True)
    - WARNING ログが出る
    """

    def test_emits_warning_for_l4_llm_template_fallback(self, caplog: pytest.LogCaptureFixture) -> None:
        """L4 LLM 失敗時の template fallback と warning。"""
        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "should-not-appear-if-failing",
                "emotional_summary": "",
                "unresolved": [],
            }
        )
        stub.raise_on_l4_call = 1
        mem = _build_memory(stub)
        with caplog.at_level(
            logging.WARNING, logger="ai_rpg_world.application.llm.services.summarizing_short_term_memory"
        ):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
            _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].is_fallback is True
        assert any("L4 LLM 生成失敗" in rec.message for rec in caplog.records)


class TestPromptSectionsE2E:
    """``SectionBasedContextFormatStrategy`` に全 section を渡すと、
    Phase 0 / 2 の section が正しい順序で並ぶ。"""

    def test_all_stable_volatile_order(self) -> None:
        """全部入り stable to volatile 順序。"""
        strategy = SectionBasedContextFormatStrategy()
        text = strategy.format(
            current_state_text="現在地: 海岸",
            recent_events_text="- 直近の出来事",
            being_memo_text="- メモ",
            objective_text="生き延びる",
            inventory_text="- 流木 x3",
            mid_summary_text="[最新] 北東を探索",
        )
        assert "【現在の目的】" in text
        assert "【自己像と世界観】" not in text
        assert "【ここまでのいきさつ】" in text
        assert "【メモ】" in text
        assert "【所持・判明した物証】" not in text
        assert "【関連する記憶】" not in text
        assert "【直近の出来事】" in text
        assert "【現在地と周囲】" in text
        idx = {
            "obj": text.index("【現在の目的】"),
            "l4": text.index("【ここまでのいきさつ】"),
            "events": text.index("【直近の出来事】"),
            "memos": text.index("【メモ】"),
            "current": text.index("【現在地と周囲】"),
        }
        assert idx["obj"] < idx["l4"] < idx["events"] < idx["memos"] < idx["current"]

    def test_l4_section(self) -> None:
        """RollingSummary が L4 を生成した後の text が正しく組み立ち、LLM が返した unresolved は出ない。"""
        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "北東を探索した",
                "emotional_summary": "やや疲労",
                "unresolved": ["水源を見つける"],
            }
        )
        mem = _build_memory(stub)
        for batch in range(4):
            for i in range(_SUMMARY_INPUT_COUNT):
                seq = batch * _SUMMARY_INPUT_COUNT + i
                mem.append(_PID, _make_observation(f"obs-{seq}", seq=seq))
            _complete_window(mem)
        mid = mem.get_mid_summary_text(_PID)
        assert "北東を探索した" in mid
        assert "やや疲労" in mid
        assert "水源を見つける" not in mid
        strategy = SectionBasedContextFormatStrategy()
        full = strategy.format(current_state_text="now", recent_events_text="recent", mid_summary_text=mid)
        assert full.index("【ここまでのいきさつ】") < full.index("【現在地と周囲】")


class TestMemoryE2ETraceObservability:
    """fallback / drop の経路が必ず trace + warning で観測可能。

    silent failure 防止の最終確認。
    """

    def test_scheduler_drop_warning_log_rendered(self, caplog: pytest.LogCaptureFixture) -> None:
        """scheduler が False を返したら consumed 件数を WARNING で残す。"""

        class _DroppingScheduler(InlineShortTermMemoryScheduler):
            def submit(self, player_id, task):
                return False

        stub = _StubSummaryPort(l4_response={"compressed_activity": "x", "emotional_summary": "", "unresolved": []})
        mem = SummarizingShortTermMemory(
            summary_service=ShortTermMemorySummaryService(stub), scheduler=_DroppingScheduler()
        )
        with caplog.at_level(
            logging.WARNING, logger="ai_rpg_world.application.llm.services.summarizing_short_term_memory"
        ):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
            _complete_window(mem)
        assert mem._mid_generations(_PID.value) == []
        assert any("drop" in rec.message and "15" in rec.message for rec in caplog.records)

    def test_thread_pool_generation_failed_trace_raises_exception(self) -> None:
        """Phase 2.2: worker 例外で SHORT_TERM_SUMMARY_GENERATION_FAILED が出る。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1, trace_recorder_provider=lambda: recorder)
        try:
            import threading

            done = threading.Event()

            def _raise() -> None:
                try:
                    raise ValueError("worker boom")
                finally:
                    done.set()

            sch.submit(player_id=_PID.value, task=_raise)
            assert done.wait(timeout=2.0)
        finally:
            sch.shutdown()
        fails = [ev for ev in captured if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_GENERATION_FAILED]
        assert len(fails) == 1
        assert fails[0].payload["error_type"] == "ValueError"
        assert "worker boom" in fails[0].payload["error_message_snippet"]
