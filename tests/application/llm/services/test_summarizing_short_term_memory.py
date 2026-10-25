"""``SummarizingShortTermMemory`` の挙動テスト (Phase 2)。

- L1 raw queue の append / get_recent
- 自分の完了ターン数が上限へ達したときの L4 生成
- L4 世代数の上限 (3)
- service 未注入時の template fallback
- LLM 失敗時の template fallback + warning
- get_mid_summary_text の整形
- persona_resolver の失敗耐性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    ThreadPoolShortTermMemoryScheduler,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
    _ParsedSummary,
)
from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
    SummarizingShortTermMemory,
    format_mid_summary_block,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SUMMARY_INPUT_COUNT = 15


def _obs(prose: str = "p", seq: int = 0) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        output=ObservationOutput(prose=prose, structured={}),
    )


@dataclass
class _StubSummaryService(ShortTermMemorySummaryService):
    """ShortTermMemorySummaryService の generate を stub する。

    parent の __init__ 制約 (port が必要) を回避するため object.__new__ 経由。
    """

    result: _ParsedSummary | None = None
    exc: Exception | None = None
    call_count: int = 0

    @classmethod
    def make(cls, *, result=None, exc=None) -> _StubSummaryService:
        inst = object.__new__(cls)
        inst.result = result
        inst.exc = exc
        inst.call_count = 0
        return inst

    def generate(self, **kwargs) -> _ParsedSummary:  # type: ignore[override]
        self.call_count += 1
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


_PID = PlayerId(7)


def _complete_window(mem: SummarizingShortTermMemory) -> None:
    """open bucket を閉じ、実際に cap までターンを進めて畳みを起こす。"""
    for _ in range(mem._turn_cap):
        mem.complete_turn(_PID)


class _CompactionTraceRecorder:
    """短期記憶圧縮の trace payload を保持する。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.records.append((kind, payload))


def test_compaction_records_tick_turn_count_and_entry_counts() -> None:
    """rolling summary は要約結果と別に、圧縮の tick・ターン数・前後件数を残す。"""
    recorder = _CompactionTraceRecorder()
    memory = SummarizingShortTermMemory(
        turn_cap=2,
        compact_turn_count=1,
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 17,
    )
    memory.append(_PID, _obs("残す出来事"))

    memory.complete_turn(_PID)
    memory.complete_turn(_PID)

    compacted = [payload for kind, payload in recorder.records if kind == TraceEventKind.SHORT_TERM_MEMORY_COMPACTED]
    assert compacted == [
        {
            "tick": 17,
            "player_id": 7,
            "completed_turn_count_before": 2,
            "completed_turn_count_after": 1,
            "entry_count_before": 1,
            "entry_count_after": 0,
            "compacted_turn_count": 1,
        }
    ]


# ──────────────────────────────────────────────────────────────────
# Basic queue behavior
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryBasicQueue:
    """L1 raw の append / get_recent の挙動。"""

    def test_append_get_recent_rendered(self) -> None:
        """append すると getrecent に新しい順で出る。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p1", seq=1))
        mem.append(_PID, _obs("p2", seq=2))
        recent = mem.get_recent(_PID, limit=10)
        proses = [o.output.prose for o in recent]
        assert proses == ["p2", "p1"]

    def test_append_all_order_append(self) -> None:
        """appendall は順番に append する。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        mem.append_all(_PID, [_obs("p1", seq=1), _obs("p2", seq=2)])

        assert len(mem.get_recent(_PID, limit=10)) == 2

    def test_actions_are_not_included_in_the_l4_summary_input(
        self,
    ) -> None:
        """行動を同じストアへ積んでも、L4 の入力には観測だけを渡す。"""
        from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
        from ai_rpg_world.application.llm.services.unified_recent_event_store import (
            UnifiedRecentEventStore,
        )

        store = UnifiedRecentEventStore()
        mem = SummarizingShortTermMemory(summary_service=None, event_store=store)
        for index in range(30):
            store.append_action_result(
                _PID,
                ActionResultEntry(
                    occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    action_summary=f"行動{index}",
                    result_summary="成功",
                ),
            )
        for index in range(14):
            mem.append(_PID, _obs(f"観測{index}"))
        assert mem._mid_generations(_PID.value) == []
        assert mem._raw_queue_len(_PID.value) == 14

        mem.append(_PID, _obs("15件目"))
        _complete_window(mem)

        assert len(mem._mid_generations(_PID.value)) == 1
        assert mem._raw_queue_len(_PID.value) == 0

    def test_get_recent_limit_zero_less_empty_list(self) -> None:
        """getrecent の limit が 0 以下は空 list。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p", seq=1))
        assert mem.get_recent(_PID, limit=0) == []
        assert mem.get_recent(_PID, limit=-1) == []

    def test_append_player_empty_list(self) -> None:
        """未 append な player は空 list。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        assert mem.get_recent(_PID, limit=10) == []
        assert mem.get_mid_summary_text(_PID) == ""


# ──────────────────────────────────────────────────────────────────
# Trigger and generation
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryTrigger:
    """自分の完了ターン数が上限へ達したときだけ L4 生成が発火する。"""

    def test_turn_cap_summarizes_only_oldest_compacted_turns(self) -> None:
        """cap 到達時は古い K ターンの観測だけを L4 にし、残りを L1 に保つ。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(
            summary_service=stub,
            turn_cap=4,
            compact_turn_count=2,
        )

        for turn in range(4):
            mem.append(_PID, _obs(f"turn-{turn}", seq=turn))
            mem.complete_turn(_PID)

        generation = mem._mid_generations(_PID.value)[0]
        assert generation.raw_count == 2
        assert [entry.output.prose for entry in reversed(mem.get_recent(_PID, 20))] == [
            "turn-2",
            "turn-3",
        ]

    def test_compaction_sends_observation_and_own_action_to_l4(self) -> None:
        """畳まれたターンの観測と実際の行動を、同じ統一 entry 群で L4 へ渡す。"""
        captured: dict[str, object] = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self) -> None:
                pass

            def generate(self, **kwargs):  # type: ignore[override]
                captured.update(kwargs)
                return _ParsedSummary(
                    compressed_activity="ok",
                    emotional_summary="",
                )

        store = UnifiedRecentEventStore()
        mem = SummarizingShortTermMemory(
            summary_service=_RecordingService(),
            event_store=store,
            turn_cap=2,
            compact_turn_count=1,
        )
        mem.append(_PID, _obs("配線箱を見つけた"))
        store.append_action_result(
            _PID,
            ActionResultEntry(
                occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                action_summary="配線の結束を締め直した",
                result_summary="成功した。",
            ),
        )
        mem.complete_turn(_PID)
        mem.complete_turn(_PID)

        events = captured["events"]
        assert isinstance(events, list)
        assert [entry.kind for entry in events] == ["observation", "action_result"]
        assert events[1].payload.action_summary == "配線の結束を締め直した"
        assert captured["compacted_turn_count"] == 1

    def test_action_only_turn_still_creates_l4(self) -> None:
        """畳むターンに行動しか無くても、その行動を L4 生成へ渡す。"""
        captured: dict[str, object] = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self) -> None:
                pass

            def generate(self, **kwargs):  # type: ignore[override]
                captured.update(kwargs)
                return _ParsedSummary(
                    compressed_activity="ok",
                    emotional_summary="",
                )

        store = UnifiedRecentEventStore()
        mem = SummarizingShortTermMemory(
            summary_service=_RecordingService(),
            event_store=store,
            turn_cap=2,
            compact_turn_count=1,
        )
        store.append_action_result(
            _PID,
            ActionResultEntry(
                occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                action_summary="発電機を点検した",
                result_summary="成功した。",
            ),
        )
        mem.complete_turn(_PID)
        mem.complete_turn(_PID)

        events = captured["events"]
        assert isinstance(events, list)
        assert [entry.kind for entry in events] == ["action_result"]
        assert events[0].payload.action_summary == "発電機を点検した"

    def test_observations_alone_do_not_create_l4(self) -> None:
        """観測を追加しただけでは、件数にかかわらず L4 は生成されない。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(summary_service=stub)
        for i in range(_SUMMARY_INPUT_COUNT - 1):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        assert stub.call_count == 0
        assert mem._mid_generations(_PID.value) == []
        assert mem._raw_queue_len(_PID.value) == _SUMMARY_INPUT_COUNT - 1

    def test_turn_cap_creates_l4_and_reduces_l1(self) -> None:
        """本人ターンが上限へ達すると、古い観測を L4 へ畳んで L1 を減らす。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="北東を探索",
                emotional_summary="疲労",
            )
        )
        mem = SummarizingShortTermMemory(summary_service=stub)
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        assert stub.call_count == 1
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].compressed_activity == "北東を探索"
        assert gens[0].is_fallback is False
        # 古い 15 件は L4 に畳まれて L1 から消える
        assert mem._raw_queue_len(_PID.value) == 0

    def test_l4_three(self) -> None:
        """L4 は 3世代までで 最古を破棄。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(summary_service=stub)
        # 4 世代分積む (= 15 * 4 = 60 件)
        for batch in range(4):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"b{batch}-{i}", seq=batch * 100 + i))
            _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        # 最新 3 世代だけ保持
        assert len(gens) == 3
        # 4 回 LLM 呼ばれた
        assert stub.call_count == 4

    def test_l4_append_left(self) -> None:
        """L4 は新しい順に appendleft される。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(summary_service=stub)
        for batch in range(2):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
            _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        # 直近世代が index 0
        assert gens[0].generated_at >= gens[1].generated_at


class TestRollingSummaryServiceNone:
    """summary_service=None でも本人ターン上限で template fallback L4 を生成する。

    sliding window 等価ではなく、「LLM なしモード」。L1 を無限に増やさない
    ため、本人ターン上限へ達したときに必ず L4 を生やす方針。
    """

    def test_turn_cap_creates_template_fallback_l4(self) -> None:
        """本人ターン上限へ達すると template fallback で L4 を生やす。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        for i in range(_SUMMARY_INPUT_COUNT + 5):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        # service=None でも本人ターン上限で template fallback L4 を作る
        assert len(gens) >= 1
        assert all(g.is_fallback for g in gens)


class TestRollingSummaryLLMFailure:
    """LLM 失敗時は template fallback + warning ログを出す。"""

    def test_llm_exception_uses_template_fallback(self, caplog: pytest.LogCaptureFixture) -> None:
        """LLM 例外なら templatefallback に縮退。"""
        stub = _StubSummaryService.make(exc=LlmApiCallException("sim", error_code="LLM_API_CALL_FAILED"))
        mem = SummarizingShortTermMemory(summary_service=stub)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.summarizing_short_term_memory",
        ):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"p{i}", seq=i))
            _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].is_fallback is True
        assert any("LLM 生成失敗" in rec.message for rec in caplog.records)

    def test_llm_fallback_raises_value_error(self) -> None:
        """LLM の ValueError でも fallback。"""
        stub = _StubSummaryService.make(exc=ValueError("parse failed"))
        mem = SummarizingShortTermMemory(summary_service=stub)
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        gens = mem._mid_generations(_PID.value)
        assert gens[0].is_fallback is True

    def test_observation_count_alone_does_not_trigger_summary(self) -> None:
        """観測件数が多くても、自分のターン境界までは L4 を生成しない。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(
            summary_service=stub,
            turn_cap=3,
            compact_turn_count=1,
        )

        for i in range(100):
            mem.append(_PID, _obs(f"p{i}", seq=i))

        assert stub.call_count == 0
        mem.complete_turn(_PID)
        mem.complete_turn(_PID)
        assert stub.call_count == 0
        mem.complete_turn(_PID)
        assert stub.call_count == 1


class TestRollingSummaryMidSummaryText:
    """get_mid_summary_text の整形。"""

    def test_returns_empty_when_l4_empty_string(self) -> None:
        """L4 が空なら空文字。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        assert mem.get_mid_summary_text(_PID) == ""

    def test_first_rendered(self) -> None:
        """最新世代が 先頭で 出る。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="今日の動き",
                emotional_summary="気分1",
            )
        )
        mem = SummarizingShortTermMemory(summary_service=stub)
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        text = mem.get_mid_summary_text(_PID)
        assert "[最新]" in text
        assert "今日の動き" in text
        assert "気分1" in text


class TestRollingSummaryPersonaResolver:
    """persona_resolver が失敗しても prompt 構築を止めない。"""

    def test_resolver_exception_falls_back_to_default(self, caplog: pytest.LogCaptureFixture) -> None:
        """resolver の例外は default に縮退する。"""
        called_with_args: dict = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(
                self,
                *,
                player_name,
                persona_block,
                events,
                compacted_turn_count,
                previous_l4=None,
            ):  # type: ignore[override]
                called_with_args["player_name"] = player_name
                called_with_args["persona_block"] = persona_block
                return _ParsedSummary(compressed_activity="x", emotional_summary="")

        def broken(pid: int):
            raise RuntimeError("oops")

        mem = SummarizingShortTermMemory(
            summary_service=_RecordingService(),
            persona_resolver=broken,
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.summarizing_short_term_memory",
        ):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"p{i}", seq=i))
            _complete_window(mem)
        assert called_with_args["player_name"] == f"Player {_PID.value}"
        assert called_with_args["persona_block"] == ""

    def test_resolver_unspecified_default_player_x_works(self) -> None:
        """resolver 未指定なら default の player X 名で 動く。"""
        called: dict = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(
                self,
                *,
                player_name,
                persona_block,
                events,
                compacted_turn_count,
                previous_l4=None,
            ):  # type: ignore[override]
                called["name"] = player_name
                return _ParsedSummary(compressed_activity="x", emotional_summary="")

        mem = SummarizingShortTermMemory(summary_service=_RecordingService())
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        assert called["name"] == f"Player {_PID.value}"


# ──────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryValidation:
    """constructor の不変条件。"""

    def test_turn_cap_must_be_greater_than_compaction_count(self) -> None:
        """畳んだ後にターン窓が空になる設定は拒否する。"""
        with pytest.raises(ValueError, match="compact_turn_count < turn_cap"):
            SummarizingShortTermMemory(turn_cap=10, compact_turn_count=10)

    def test_keep_generations_zero_less_value_error(self) -> None:
        """keep generations が 0以下なら value error。"""
        with pytest.raises(ValueError, match="l4_keep_generations"):
            SummarizingShortTermMemory(l4_keep_generations=0)

    def test_service_non_short_term_memory_summary_service_type_error(self) -> None:
        """service が非 ShortTermMemorySummaryService なら typeerror。"""
        with pytest.raises(TypeError, match="summary_service"):
            SummarizingShortTermMemory(summary_service="not-a-service")  # type: ignore[arg-type]

    def test_persona_resolver_callable_type_error(self) -> None:
        """persona resolver が callable でなければ type error。"""
        with pytest.raises(TypeError, match="persona_resolver"):
            SummarizingShortTermMemory(persona_resolver="not-callable")  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────
# format_mid_summary_block
# ──────────────────────────────────────────────────────────────────


class TestFormatMidSummaryBlock:
    """prompt 用の text 整形。"""

    def test_empty_input_empty_string(self) -> None:
        """空 input は空文字。"""
        assert format_mid_summary_block([]) == ""

    def test_first_label(self) -> None:
        """先頭世代に 最新 ラベルが 付く。"""
        gens = [
            L4MidSummary(
                summary_id=f"l4-{i}",
                player_id=1,
                raw_count=15,
                generated_at=datetime(2026, 6, 1, 12, i, tzinfo=timezone.utc),
                compressed_activity=f"動き{i}",
                emotional_summary=f"気分{i}",
            )
            for i in range(2)
        ]
        text = format_mid_summary_block(gens)
        assert "[最新]" in text.splitlines()[0]
        # 2 世代目には [2 世代前] ラベル
        assert "[2 世代前]" in text

    def test_returns_empty_when_emotional_summary_empty(self) -> None:
        """emotional_summary が空なら気分の行が出ず、片付いていないことの行も無い。"""
        gen = L4MidSummary(
            summary_id="l4-1",
            player_id=1,
            raw_count=15,
            generated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            compressed_activity="動き",
            emotional_summary="",
        )
        text = format_mid_summary_block([gen])
        assert "気分" not in text
        assert "未解決" not in text


# ──────────────────────────────────────────────────────────────────
# Phase 2.1: scheduler 統合
# ──────────────────────────────────────────────────────────────────


class TestRollingSummarySchedulerIntegration:
    """scheduler 経由の L4 生成 (Inline / ThreadPool)。"""

    def test_default_scheduler_inline(self) -> None:
        """default scheduler は Inline。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        # default は Inline (= 同期実行)
        assert isinstance(mem._scheduler, InlineShortTermMemoryScheduler)

    def test_inline_scheduler_works(self) -> None:
        """明示 Inline scheduler でも 動く。"""
        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(
            summary_service=stub,
            scheduler=InlineShortTermMemoryScheduler(),
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        _complete_window(mem)
        # Inline は同期なので submit 後すぐに L4 が見える
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1

    def test_thread_pool_scheduler_l4_non_install(self) -> None:
        """ThreadPool: submit は即時 return、L4 install は worker thread が完了させる。"""
        import threading

        gate = threading.Event()

        class _SlowService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(self, **kwargs):  # type: ignore[override]
                gate.wait(timeout=2.0)
                return _ParsedSummary(
                    compressed_activity="slow result",
                    emotional_summary="",
                )

        scheduler = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        try:
            mem = SummarizingShortTermMemory(
                summary_service=_SlowService(),
                scheduler=scheduler,
            )
            # 観測を積み、本人ターン上限へ到達させる。L4 は worker 完了まで未反映。
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"p{i}", seq=i))
            _complete_window(mem)
            assert mem._mid_generations(_PID.value) == []
            # worker 解放 + shutdown で完了待ち
            gate.set()
        finally:
            # 例外経路でも worker が hang しないよう gate を必ず set。
            # shutdown は 1 回だけ呼ぶ (review MEDIUM #5: 旧版は二重呼び出し)
            gate.set()
            scheduler.shutdown()
        # shutdown 完了後にアサート (この時点で in-flight task が install 済み)
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].compressed_activity == "slow result"

    def test_scheduler_non_ishort_term_memory_scheduler_type_error(self) -> None:
        """scheduler が非 IShortTermMemoryScheduler なら typeerror。"""
        with pytest.raises(TypeError, match="scheduler"):
            SummarizingShortTermMemory(scheduler="not-a-scheduler")  # type: ignore[arg-type]

    def test_emits_warning_for_scheduler_drop_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """review HIGH #1: scheduler.submit が False を返すと observations は
        L1 / L4 から消える silent data loss になる。consumed 件数を WARNING
        ログに残して可観測化する。"""

        class _DroppingScheduler(InlineShortTermMemoryScheduler):
            def submit(self, player_id, task):  # type: ignore[override]
                return False  # 常に drop

        stub = _StubSummaryService.make(result=_ParsedSummary(compressed_activity="ok", emotional_summary=""))
        mem = SummarizingShortTermMemory(
            summary_service=stub,
            scheduler=_DroppingScheduler(),
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.summarizing_short_term_memory",
        ):
            for i in range(_SUMMARY_INPUT_COUNT):
                mem.append(_PID, _obs(f"p{i}", seq=i))
            _complete_window(mem)
        # consumed は popleft 済みなので L1 = 0、L4 install もされず L4 = 0
        assert mem._raw_queue_len(_PID.value) == 0
        assert mem._mid_generations(_PID.value) == []
        # WARNING ログに件数が含まれる
        assert any("drop" in rec.message and "15" in rec.message for rec in caplog.records)

    def test_shutdown_scheduler(self) -> None:
        """shutdown は scheduler に委譲。"""
        called = {"n": 0}

        class _RecordingScheduler(InlineShortTermMemoryScheduler):
            def shutdown(self, timeout=None):
                called["n"] += 1

        mem = SummarizingShortTermMemory(scheduler=_RecordingScheduler())
        mem.shutdown()
        assert called["n"] == 1


class _RecordingRecorder:
    """trace recorder の test 用 fake。`record(kind, **payload)` を全部保持する。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, kind: str, **payload) -> None:  # type: ignore[no-untyped-def]
        self.events.append({"kind": kind, **payload})


class TestShortTermSummaryGeneratedTrace:
    """PR #435: L4 が install された瞬間の trace 出力 (成功 / fallback 両方)。

    成功時の生成内容は従来 trace に出ず、'rolling が何を圧縮したか' が事後追え
    なかった。実験 #30 前準備でギャップとして発覚し、本トレースで埋める。
    """

    def test_l4_install_short_term_summary_generated_emit(self) -> None:
        """LLM 成功経路で L4 が install されたら 1 件 trace に出る。"""
        rec = _RecordingRecorder()
        parsed = _ParsedSummary(
            compressed_activity="森でキノコを採集した",
            emotional_summary="やや疲れた",
        )
        mem = SummarizingShortTermMemory(
            summary_service=_StubSummaryService.make(result=parsed),
            trace_recorder_provider=lambda: rec,
            current_tick_provider=lambda: 42,
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        # L4 trace が 1 件出る
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        ev = l4_events[0]
        assert ev["player_id"] == _PID.value
        assert ev["tick"] == 42
        assert ev["raw_count"] == _SUMMARY_INPUT_COUNT
        assert ev["compressed_activity"] == "森でキノコを採集した"
        assert ev["emotional_summary"] == "やや疲れた"
        assert "unresolved" not in ev
        assert ev["is_fallback"] is False
        assert ev["summary_id"].startswith("l4-")

    def test_template_fallback_trace_fallback_true(self) -> None:
        """summary_service=None でも (LLM なしモード) template fallback で trace。"""
        rec = _RecordingRecorder()
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        assert l4_events[0]["is_fallback"] is True

    def test_missing_recorder_provider_is_no_op_without_exception(self) -> None:
        """既存挙動の後方互換: provider 未指定なら trace は出ず、本体は動く。"""
        mem = SummarizingShortTermMemory(summary_service=None)
        # 例外を投げずに L4 install まで通る
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        # mid summary は生成されている
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_recorder_provider_exception_does_not_stop_summary(self) -> None:
        """trace recorder の I/O 失敗が L4 install を倒さないこと (best-effort)。"""

        def boom() -> object:
            raise RuntimeError("recorder broken")

        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=boom,
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_current_tick_provider_none_tick_none(self) -> None:
        """tick provider 未指定なら trace の tick は None になる (recorder には届く)。"""
        rec = _RecordingRecorder()
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
            # current_tick_provider 未指定
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert l4_events[0]["tick"] is None


class TestPostHocSetters:
    """PR #439: trace_recorder_provider / current_tick_provider / summary_services
    を runtime 構築後に注入できる setter。world_runtime 等で必要。"""

    def test_set_trace_recorder_provider_emit(self) -> None:
        """ctor で None 渡し → setter で注入 → L4 install 時に trace 出る。"""
        rec = _RecordingRecorder()
        mem = SummarizingShortTermMemory(summary_service=None)
        # 最初は provider 未設定
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len([e for e in rec.events if e["kind"] == "short_term_summary_generated"]) == 0

        # setter で注入
        mem.set_trace_recorder_provider(lambda: rec)
        mem.set_current_tick_provider(lambda: 77)
        # 次の L4 cycle で trace が出る
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o2_{i}", seq=100 + i))
        _complete_window(mem)
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        assert l4_events[0]["tick"] == 77

    def test_returns_set_trace_recorder_provider_none_op(self) -> None:
        """provider=None で再び no-op (= 過去のセットアップを解除可能)。"""
        rec = _RecordingRecorder()
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        mem.set_trace_recorder_provider(None)
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        assert len([e for e in rec.events if e["kind"] == "short_term_summary_generated"]) == 0

    # PR #451 (PR 6/6): set_summary_services は廃止。ctor 注入に統一されたので、
    # 旧 setter テスト 2 件は削除。LLM 経路の test は ctor で services を渡す
    # 形に書き直し済 (TestRollingSummaryTrigger 等)。


class TestTraceRecorderNullObjectNormalization:
    """PR #449 (PR 4/6): trace_recorder_provider が None / 例外 / None 返却の
    すべてのパターンで NullTraceRecorder にフォールバックする (= NullObject)。

    旧来は ``if provider is None`` / ``if recorder is None`` の silent skip 経路で
    分岐していたが、PR #449 で `_ensure_trace_recorder_provider` 経由の正規化に
    統一した。本テストは emit 経路が常に recorder.record() を 1 度呼べる構造を
    保証する。
    """

    def test_provider_none_emit_raises_exception(self) -> None:
        """ctor で None を渡しても emit は NullTraceRecorder に流れる。"""
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=None,
        )
        # 例外なく L4 install まで通る
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_provider_null_trace_recorder_raises_exception(self) -> None:
        """provider 自体が raise するケースでも本体は止まらない。"""

        def boom() -> object:
            raise RuntimeError("recorder broken")

        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=boom,
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_returns_null_trace_recorder_fallback_provider_none_even_if(self) -> None:
        """lazy lookup で recorder 未確定の場合 (provider が None を返す) でも emit する。"""
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: None,
        )
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_setter_via(self) -> None:
        """set_trace_recorder_provider(None) で no-op に戻しても emit は安全。"""
        rec = _RecordingRecorder()
        mem = SummarizingShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        mem.set_trace_recorder_provider(None)  # ← None で解除
        for i in range(_SUMMARY_INPUT_COUNT):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        _complete_window(mem)
        # rec には record されないが、本体は動く
        assert len([e for e in rec.events if e["kind"] == "short_term_summary_generated"]) == 0
        assert len(mem._mid_generations(_PID.value)) == 1


class TestRollingSummaryCompactionListener:
    """SummarizingShortTermMemory が畳んだ範囲を、要約とは別に聞き手へ渡すことを保証する。"""

    def test_listener_receives_exactly_the_compacted_entries(self) -> None:
        """畳むとき、聞き手には畳んだ古いターンの出来事だけが、要約に渡すものと同じ並びで渡る。"""
        received: list[tuple[PlayerId, list[str]]] = []
        mem = SummarizingShortTermMemory(
            turn_cap=4,
            compact_turn_count=2,
            on_compacted=lambda pid, entries: received.append((pid, [e.payload.output.prose for e in entries])),
        )

        for turn in range(4):
            mem.append(_PID, _obs(f"turn-{turn}", seq=turn))
            mem.complete_turn(_PID)

        assert received == [(_PID, ["turn-0", "turn-1"])]

    def test_listener_is_not_called_before_the_cap(self) -> None:
        """ターン数が上限に届くまでは、聞き手を呼ばない。"""
        received: list[object] = []
        mem = SummarizingShortTermMemory(
            turn_cap=4, compact_turn_count=2, on_compacted=lambda pid, entries: received.append(entries)
        )

        for turn in range(3):
            mem.append(_PID, _obs(f"turn-{turn}", seq=turn))
            mem.complete_turn(_PID)

        assert received == []

    def test_listener_failure_does_not_stop_the_summary(self) -> None:
        """聞き手が例外を投げても、要約は作られ、complete_turn は例外を出さない。"""

        def _broken(pid: PlayerId, entries: object) -> None:
            raise RuntimeError("boom")

        mem = SummarizingShortTermMemory(turn_cap=2, compact_turn_count=1, on_compacted=_broken)
        mem.append(_PID, _obs("turn-0"))
        mem.complete_turn(_PID)
        mem.complete_turn(_PID)

        assert len(mem._mid_generations(_PID.value)) == 1

    def test_listener_still_receives_the_range_when_the_summary_submit_fails(self) -> None:
        """要約の送信が例外を投げても、短期記憶から外れた範囲は聞き手に渡る。"""
        received: list[object] = []

        class _BrokenScheduler(InlineShortTermMemoryScheduler):
            def submit(self, pid, task):  # type: ignore[override]
                raise RuntimeError("scheduler down")

        mem = SummarizingShortTermMemory(
            turn_cap=2,
            compact_turn_count=1,
            scheduler=_BrokenScheduler(),
            on_compacted=lambda pid, entries: received.append(entries),
        )
        mem.append(_PID, _obs("turn-0"))
        mem.complete_turn(_PID)

        with pytest.raises(RuntimeError):
            mem.complete_turn(_PID)

        assert len(received) == 1

    def test_uncompacted_entries_include_the_open_turn(self) -> None:
        """まだ畳んでいない分は、閉じたターンと、まだ閉じていないターンの出来事を古い順に含む。"""
        mem = SummarizingShortTermMemory(turn_cap=4, compact_turn_count=2)
        mem.append(_PID, _obs("closed"))
        mem.complete_turn(_PID)
        mem.append(_PID, _obs("open"))

        assert [e.payload.output.prose for e in mem.uncompacted_entries(_PID)] == ["closed", "open"]
