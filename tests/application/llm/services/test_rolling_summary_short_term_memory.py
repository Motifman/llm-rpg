"""``RollingSummaryShortTermMemory`` の挙動テスト (Phase 2)。

- L1 raw queue の append / get_recent
- soft cap (15) 到達で L4 生成 trigger
- L4 世代数の上限 (3)
- service 未注入で L4 生成スキップ (= sliding window 等価)
- LLM 失敗時の template fallback + warning
- get_mid_summary_text の整形
- persona_resolver の失敗耐性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

import pytest

from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)
from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
    ShortTermMemoryLongSummaryService,
    _ParsedLongSummary,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
    DEFAULT_L1_SOFT_CAP,
    RollingSummaryShortTermMemory,
    format_mid_summary_block,
)
from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    ThreadPoolShortTermMemoryScheduler,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
    _ParsedSummary,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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
    def make(cls, *, result=None, exc=None) -> "_StubSummaryService":
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


# ──────────────────────────────────────────────────────────────────
# Basic queue behavior
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryBasicQueue:
    """L1 raw の append / get_recent の挙動。"""

    def test_append_get_recent_rendered(self) -> None:
        """append すると getrecent に新しい順で出る。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p1", seq=1))
        mem.append(_PID, _obs("p2", seq=2))
        recent = mem.get_recent(_PID, limit=10)
        proses = [o.output.prose for o in recent]
        assert proses == ["p2", "p1"]

    def test_append_all_order_append(self) -> None:
        """appendall は順番に append する。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        evicted = mem.append_all(_PID, [_obs("p1", seq=1), _obs("p2", seq=2)])
        # rolling 実装は evict せず L4 に畳むので overflow は空
        assert evicted == []
        assert len(mem.get_recent(_PID, limit=10)) == 2

    def test_get_recent_limit_zero_less_empty_list(self) -> None:
        """getrecent の limit が 0 以下は空 list。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p", seq=1))
        assert mem.get_recent(_PID, limit=0) == []
        assert mem.get_recent(_PID, limit=-1) == []

    def test_append_player_empty_list(self) -> None:
        """未 append な player は空 list。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        assert mem.get_recent(_PID, limit=10) == []
        assert mem.get_mid_summary_text(_PID) == ""


# ──────────────────────────────────────────────────────────────────
# Trigger and generation
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryTrigger:
    """soft cap (15) 到達で L4 生成 trigger が発火する。"""

    def test_fifteen_below_l4(self) -> None:
        """15 件未満なら L4 は生成されない。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP - 1):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        assert stub.call_count == 0
        assert mem._mid_generations(_PID.value) == []
        assert mem._raw_queue_len(_PID.value) == DEFAULT_L1_SOFT_CAP - 1

    def test_fifteen_l4_l1(self) -> None:
        """15 件目で L4 を生成し L1 を減らす。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="北東を探索",
                emotional_summary="疲労",
                unresolved=("水源",),
            )
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        assert stub.call_count == 1
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].compressed_activity == "北東を探索"
        assert gens[0].is_fallback is False
        # 古い 15 件は L4 に畳まれて L1 から消える
        assert mem._raw_queue_len(_PID.value) == 0

    def test_l4_three(self) -> None:
        """L4 は 3世代までで 最古を破棄。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="ok", emotional_summary="", unresolved=()
            )
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        # 4 世代分積む (= 15 * 4 = 60 件)
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}-{i}", seq=batch * 100 + i))
        gens = mem._mid_generations(_PID.value)
        # 最新 3 世代だけ保持
        assert len(gens) == 3
        # 4 回 LLM 呼ばれた
        assert stub.call_count == 4

    def test_l4_append_left(self) -> None:
        """L4 は新しい順に appendleft される。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="ok", emotional_summary="", unresolved=()
            )
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for batch in range(2):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        gens = mem._mid_generations(_PID.value)
        # 直近世代が index 0
        assert gens[0].generated_at >= gens[1].generated_at


class TestRollingSummaryServiceNone:
    """summary_service=None でも soft cap 到達で template fallback L4 を生成する。

    sliding window 等価ではなく、「LLM なしモード」。L1 を無限に増やさない
    ため、soft cap 到達時に必ず L4 を生やす方針。
    """

    def test_fifteen_exceeds_template_fallback_l4(self) -> None:
        """15 件超えると templatefallback で L4 を生やす。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        for i in range(DEFAULT_L1_SOFT_CAP + 5):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        # service=None でも 15 件超は template fallback で L4 を作る
        assert len(gens) >= 1
        assert all(g.is_fallback for g in gens)


class TestRollingSummaryLLMFailure:
    """LLM 失敗時は template fallback + warning ログを出す。"""

    def test_llm_exception_uses_template_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM 例外なら templatefallback に縮退。"""
        stub = _StubSummaryService.make(
            exc=LlmApiCallException("sim", error_code="LLM_API_CALL_FAILED")
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"p{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].is_fallback is True
        assert any("LLM 生成失敗" in rec.message for rec in caplog.records)

    def test_llm_fallback_raises_value_error(self) -> None:
        """LLM の ValueError でも fallback。"""
        stub = _StubSummaryService.make(exc=ValueError("parse failed"))
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        assert gens[0].is_fallback is True

    def test_hard_cap_llm_skip_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """L1 が hard_cap を超えた状態で trigger された場合、LLM を呼ばず
        即 template fallback に降りる (review HIGH #2 修正の確認)。

        通常の sequential append では L1 は soft_cap+1 で必ず trigger するため
        hard_cap には到達しない。これは「外部状態崩壊」(直接 _raw を改竄するなど)
        への safety belt。テストでは ``_raw`` に直接データを積むことで再現する。
        """
        attempt_count = {"n": 0}

        class _AlwaysFailService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(self, **kwargs):  # type: ignore[override]
                attempt_count["n"] += 1
                raise LlmApiCallException("simulated", error_code="LLM_API_CALL_FAILED")

        mem = RollingSummaryShortTermMemory(
            summary_service=_AlwaysFailService(),
            l1_soft_cap=5,
            l1_hard_cap=10,
        )
        mem._ensure_player(_PID.value)
        # 直接 _raw に hard_cap 件以上積む (soft_cap trigger を bypass した状況を模擬)
        for i in range(12):
            mem._raw[_PID.value].append(_obs(f"p{i}", seq=i))
        # この状態で append (= 1 件追加 + trigger) を呼ぶ
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            mem.append(_PID, _obs("trigger", seq=999))
        # hard_cap 到達経路では LLM を呼ばないので attempt_count = 0
        assert attempt_count["n"] == 0
        # 必ず L4 は生まれている (template fallback)
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].is_fallback is True
        # warning ログ
        assert any("hard cap" in rec.message for rec in caplog.records)


class TestRollingSummaryMidSummaryText:
    """get_mid_summary_text の整形。"""

    def test_returns_empty_when_l4_empty_string(self) -> None:
        """L4 が空なら空文字。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        assert mem.get_mid_summary_text(_PID) == ""

    def test_first_rendered(self) -> None:
        """最新世代が 先頭で 出る。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(
                compressed_activity="今日の動き",
                emotional_summary="気分1",
                unresolved=("X",),
            )
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        text = mem.get_mid_summary_text(_PID)
        assert "[最新]" in text
        assert "今日の動き" in text
        assert "気分1" in text
        assert "X" in text


class TestRollingSummaryPersonaResolver:
    """persona_resolver が失敗しても prompt 構築を止めない。"""

    def test_resolver_exception_falls_back_to_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """resolver の例外は default に縮退する。"""
        called_with_args: dict = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(self, *, player_name, persona_block, observations, previous_l4=None):  # type: ignore[override]
                called_with_args["player_name"] = player_name
                called_with_args["persona_block"] = persona_block
                return _ParsedSummary(compressed_activity="x", emotional_summary="", unresolved=())

        def broken(pid: int):
            raise RuntimeError("oops")

        mem = RollingSummaryShortTermMemory(
            summary_service=_RecordingService(),
            persona_resolver=broken,
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"p{i}", seq=i))
        assert called_with_args["player_name"] == f"Player {_PID.value}"
        assert called_with_args["persona_block"] == ""

    def test_resolver_unspecified_default_player_x_works(self) -> None:
        """resolver 未指定なら default の player X 名で 動く。"""
        called: dict = {}

        class _RecordingService(ShortTermMemorySummaryService):
            def __init__(self):
                pass

            def generate(self, *, player_name, persona_block, observations, previous_l4=None):  # type: ignore[override]
                called["name"] = player_name
                return _ParsedSummary(compressed_activity="x", emotional_summary="", unresolved=())

        mem = RollingSummaryShortTermMemory(summary_service=_RecordingService())
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        assert called["name"] == f"Player {_PID.value}"


# ──────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryValidation:
    """constructor の不変条件。"""

    def test_soft_cap_zero_less_value_error(self) -> None:
        """soft cap が 0以下なら value error。"""
        with pytest.raises(ValueError, match="l1_soft_cap"):
            RollingSummaryShortTermMemory(l1_soft_cap=0)

    def test_hard_cap_soft_below_value_error(self) -> None:
        """hard cap が soft 未満なら value error。"""
        with pytest.raises(ValueError, match="l1_hard_cap"):
            RollingSummaryShortTermMemory(l1_soft_cap=15, l1_hard_cap=10)

    def test_keep_generations_zero_less_value_error(self) -> None:
        """keep generations が 0以下なら value error。"""
        with pytest.raises(ValueError, match="l4_keep_generations"):
            RollingSummaryShortTermMemory(l4_keep_generations=0)

    def test_service_non_short_term_memory_summary_service_type_error(self) -> None:
        """service が非 ShortTermMemorySummaryService なら typeerror。"""
        with pytest.raises(TypeError, match="summary_service"):
            RollingSummaryShortTermMemory(summary_service="not-a-service")  # type: ignore[arg-type]

    def test_persona_resolver_callable_type_error(self) -> None:
        """persona resolver が callable でなければ type error。"""
        with pytest.raises(TypeError, match="persona_resolver"):
            RollingSummaryShortTermMemory(persona_resolver="not-callable")  # type: ignore[arg-type]


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
                unresolved=(f"item{i}",),
            )
            for i in range(2)
        ]
        text = format_mid_summary_block(gens)
        assert "[最新]" in text.splitlines()[0]
        # 2 世代目には [2 世代前] ラベル
        assert "[2 世代前]" in text

    def test_returns_empty_when_emotional_summary_unresolved(self) -> None:
        """emotionalsummary と unresolved が空なら該当行が出ない。"""
        gen = L4MidSummary(
            summary_id="l4-1",
            player_id=1,
            raw_count=15,
            generated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            compressed_activity="動き",
            emotional_summary="",
            unresolved=(),
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
        mem = RollingSummaryShortTermMemory(summary_service=None)
        # default は Inline (= 同期実行)
        assert isinstance(mem._scheduler, InlineShortTermMemoryScheduler)

    def test_inline_scheduler_works(self) -> None:
        """明示 Inline scheduler でも 動く。"""
        stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=stub,
            scheduler=InlineShortTermMemoryScheduler(),
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
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
                    unresolved=(),
                )

        scheduler = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        try:
            mem = RollingSummaryShortTermMemory(
                summary_service=_SlowService(),
                scheduler=scheduler,
            )
            # 15 件 append (trigger 発火)。Inline と違い、L4 はまだ install されていない
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"p{i}", seq=i))
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
            RollingSummaryShortTermMemory(scheduler="not-a-scheduler")  # type: ignore[arg-type]

    def test_emits_warning_for_scheduler_drop_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """review HIGH #1: scheduler.submit が False を返すと observations は
        L1 / L4 から消える silent data loss になる。consumed 件数を WARNING
        ログに残して可観測化する。"""

        class _DroppingScheduler(InlineShortTermMemoryScheduler):
            def submit(self, player_id, task):  # type: ignore[override]
                return False  # 常に drop

        stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=stub,
            scheduler=_DroppingScheduler(),
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"p{i}", seq=i))
        # consumed は popleft 済みなので L1 = 0、L4 install もされず L4 = 0
        assert mem._raw_queue_len(_PID.value) == 0
        assert mem._mid_generations(_PID.value) == []
        # WARNING ログに件数が含まれる
        assert any(
            "drop" in rec.message and "15" in rec.message for rec in caplog.records
        )

    def test_shutdown_scheduler(self) -> None:
        """shutdown は scheduler に委譲。"""
        called = {"n": 0}

        class _RecordingScheduler(InlineShortTermMemoryScheduler):
            def shutdown(self, timeout=None):
                called["n"] += 1

        mem = RollingSummaryShortTermMemory(scheduler=_RecordingScheduler())
        mem.shutdown()
        assert called["n"] == 1


# ──────────────────────────────────────────────────────────────────
# Phase 3: L5 long summary 統合
# ──────────────────────────────────────────────────────────────────


@dataclass
class _StubLongService(ShortTermMemoryLongSummaryService):
    """ShortTermMemoryLongSummaryService の generate を stub する。"""

    result: _ParsedLongSummary | None = None
    exc: Exception | None = None
    call_count: int = 0
    captured_previous_l5: L5LongSummary | None = None
    captured_evicted_l4: L4MidSummary | None = None

    @classmethod
    def make(cls, *, result=None, exc=None):
        inst = object.__new__(cls)
        inst.result = result
        inst.exc = exc
        inst.call_count = 0
        inst.captured_previous_l5 = None
        inst.captured_evicted_l4 = None
        return inst

    def generate(self, *, player_name, persona_block, previous_l5, evicted_l4):  # type: ignore[override]
        self.call_count += 1
        self.captured_previous_l5 = previous_l5
        self.captured_evicted_l4 = evicted_l4
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


class TestRollingSummaryL5Trigger:
    """L4 が keep_gen+1 世代目に達したら L5 統合 task が発火する (Phase 3)。"""

    def test_l4_three_less_l5(self) -> None:
        """L4 が 3 世代以下なら L5 は生成されない。"""
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        long_stub = _StubLongService.make(
            result=_ParsedLongSummary(self_image="self", world_view="world")
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub,
        )
        # 3 世代分積む (= 15 * 3 = 45 件)
        for batch in range(3):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        # L4 は 3 世代まで、L5 はまだ生成されない (= eviction なし)
        assert len(mem._mid_generations(_PID.value)) == 3
        assert long_stub.call_count == 0
        assert mem._long_summary(_PID.value) is None

    def test_l4_four_l5_trigger_l4_evict(self) -> None:
        """L4 が 4 世代目で L5 統合が発火最古 L4 が evict。"""
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        long_stub = _StubLongService.make(
            result=_ParsedLongSummary(
                self_image="統合された自己像",
                world_view="統合された世界観",
            )
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub,
        )
        # 4 世代分積む (= 15 * 4 = 60 件)
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        # L4 は 3 世代まで保持、最古は evict されて L5 になる
        assert len(mem._mid_generations(_PID.value)) == 3
        assert long_stub.call_count == 1
        l5 = mem._long_summary(_PID.value)
        assert l5 is not None
        assert l5.self_image == "統合された自己像"
        assert l5.world_view == "統合された世界観"
        assert l5.generation_index == 1
        assert l5.is_fallback is False

    def test_returns_l5_generation_index_l4_evict_when(self) -> None:
        """L4evict を繰り返すと L5 の generationindex が増える。"""
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        long_stub = _StubLongService.make(
            result=_ParsedLongSummary(self_image="self", world_view="world")
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub,
        )
        # 5 世代分積む (= 75 件)。L4 evict が 2 回発火
        for batch in range(5):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        assert long_stub.call_count == 2
        l5 = mem._long_summary(_PID.value)
        assert l5 is not None
        assert l5.generation_index == 2

    def test_long_service_none_template_fallback(self) -> None:
        """previous_l5 が None で long_service も None なら placeholder L5。"""
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="北を歩いた", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=None,
        )
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        l5 = mem._long_summary(_PID.value)
        assert l5 is not None
        assert l5.is_fallback is True
        # 初回 L5 で previous_l5 が無いので placeholder
        assert "未生成" in l5.self_image

    def test_llm_failure_previous_l5(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """L5 LLM が落ちても previous_l5 で延命される (persona drift 防止)。"""
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        # 最初の L5 は成功
        long_stub_first = _StubLongService.make(
            result=_ParsedLongSummary(
                self_image="安定した自己像",
                world_view="安定した世界観",
            )
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub_first,
        )
        # 4 世代分積んで L5 を 1 つ作る
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        first_l5 = mem._long_summary(_PID.value)
        assert first_l5 is not None

        # service を例外を返すものに差し替えて 5 世代目を追加
        mem._long_service = _StubLongService.make(
            exc=LlmApiCallException("sim", error_code="LLM_API_CALL_FAILED")
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b5-{i}", seq=500 + i))

        l5 = mem._long_summary(_PID.value)
        assert l5 is not None
        # previous_l5 が延命される
        assert l5.self_image == "安定した自己像"
        assert l5.world_view == "安定した世界観"
        assert l5.is_fallback is True
        assert l5.generation_index == 2
        assert any("L5 LLM 生成失敗" in rec.message for rec in caplog.records)

    def test_get_long_summary_text_self_image_world_view(self) -> None:
        """getlongsummarytext が selfimage と worldview を整形。"""
        long_stub = _StubLongService.make(
            result=_ParsedLongSummary(
                self_image="寡黙な漁師",
                world_view="島は穏やか",
            )
        )
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub,
        )
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))
        text = mem.get_long_summary_text(_PID)
        assert "私について" in text
        assert "寡黙な漁師" in text
        assert "この世界について" in text
        assert "島は穏やか" in text

    def test_get_long_summary_text_l5_empty_string(self) -> None:
        """get long summary text は L5 未生成なら 空文字。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        assert mem.get_long_summary_text(_PID) == ""

    def test_long_summary_service_non_service_type_error(self) -> None:
        """longsummaryservice が非 service なら typeerror。"""
        with pytest.raises(TypeError, match="long_summary_service"):
            RollingSummaryShortTermMemory(
                long_summary_service="not-a-service",  # type: ignore[arg-type]
            )


class _RecordingRecorder:
    """trace recorder の test 用 fake。`record(kind, **payload)` を全部保持する。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, kind: str, **payload) -> None:  # type: ignore[no-untyped-def]
        self.events.append({"kind": kind, **payload})


class TestShortTermSummaryGeneratedTrace:
    """PR #435: L4 / L5 が install された瞬間の trace 出力 (成功 / fallback 両方)。

    成功時の生成内容は従来 trace に出ず、'rolling が何を圧縮したか' が事後追え
    なかった。実験 #30 前準備でギャップとして発覚し、本トレースで埋める。
    """

    def test_l4_install_short_term_summary_generated_emit(self) -> None:
        """LLM 成功経路で L4 が install されたら 1 件 trace に出る。"""
        rec = _RecordingRecorder()
        parsed = _ParsedSummary(
            compressed_activity="森でキノコを採集した",
            emotional_summary="やや疲れた",
            unresolved=("キノコの種類不明",),
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=_StubSummaryService.make(result=parsed),
            trace_recorder_provider=lambda: rec,
            current_tick_provider=lambda: 42,
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        # L4 trace が 1 件出る
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        ev = l4_events[0]
        assert ev["player_id"] == _PID.value
        assert ev["tick"] == 42
        assert ev["raw_count"] == DEFAULT_L1_SOFT_CAP
        assert ev["compressed_activity"] == "森でキノコを採集した"
        assert ev["emotional_summary"] == "やや疲れた"
        assert ev["unresolved"] == ["キノコの種類不明"]
        assert ev["is_fallback"] is False
        assert ev["summary_id"].startswith("l4-")

    def test_template_fallback_trace_fallback_true(self) -> None:
        """summary_service=None でも (LLM なしモード) template fallback で trace。"""
        rec = _RecordingRecorder()
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        assert l4_events[0]["is_fallback"] is True

    def test_missing_recorder_provider_is_no_op_without_exception(self) -> None:
        """既存挙動の後方互換: provider 未指定なら trace は出ず、本体は動く。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        # 例外を投げずに L4 install まで通る
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        # mid summary は生成されている
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_recorder_provider_exception_does_not_stop_summary(self) -> None:
        """trace recorder の I/O 失敗が L4 install を倒さないこと (best-effort)。"""
        def boom() -> object:
            raise RuntimeError("recorder broken")

        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=boom,
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_current_tick_provider_none_tick_none(self) -> None:
        """tick provider 未指定なら trace の tick は None になる (recorder には届く)。"""
        rec = _RecordingRecorder()
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
            # current_tick_provider 未指定
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert l4_events[0]["tick"] is None

    def test_l5_install_short_term_long_summary_generated_emit(self) -> None:
        """L4 が keep_gen=3 を超えて evict されると L5 が install され、trace に 1 件出る。"""
        rec = _RecordingRecorder()
        # 4 generation 分 L4 を生成して L5 を発火させる (DEFAULT_L4_KEEP_GENERATIONS=3)
        long_stub = _StubLongService.make(
            result=_ParsedLongSummary(
                self_image="私は寡黙な観察者",
                world_view="この島は不気味",
            )
        )
        mid_stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=mid_stub,
            long_summary_service=long_stub,
            trace_recorder_provider=lambda: rec,
            current_tick_provider=lambda: 99,
        )
        for batch in range(4):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _obs(f"b{batch}", seq=batch * 100 + i))

        l5_events = [e for e in rec.events if e["kind"] == "short_term_long_summary_generated"]
        assert len(l5_events) == 1
        ev = l5_events[0]
        assert ev["player_id"] == _PID.value
        assert ev["tick"] == 99
        assert ev["generation_index"] == 1
        assert ev["self_image"] == "私は寡黙な観察者"
        assert ev["world_view"] == "この島は不気味"
        assert ev["is_fallback"] is False
        assert ev["summary_id"].startswith("l5-")


class TestPostHocSetters:
    """PR #439: trace_recorder_provider / current_tick_provider / summary_services
    を runtime 構築後に注入できる setter。world_runtime 等で必要。"""

    def test_set_trace_recorder_provider_emit(self) -> None:
        """ctor で None 渡し → setter で注入 → L4 install 時に trace 出る。"""
        rec = _RecordingRecorder()
        mem = RollingSummaryShortTermMemory(summary_service=None)
        # 最初は provider 未設定
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len([e for e in rec.events if e["kind"] == "short_term_summary_generated"]) == 0

        # setter で注入
        mem.set_trace_recorder_provider(lambda: rec)
        mem.set_current_tick_provider(lambda: 77)
        # 次の L4 cycle で trace が出る
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o2_{i}", seq=100 + i))
        l4_events = [e for e in rec.events if e["kind"] == "short_term_summary_generated"]
        assert len(l4_events) == 1
        assert l4_events[0]["tick"] == 77

    def test_returns_set_trace_recorder_provider_none_op(self) -> None:
        """provider=None で再び no-op (= 過去のセットアップを解除可能)。"""
        rec = _RecordingRecorder()
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        mem.set_trace_recorder_provider(None)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
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
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=None,
        )
        # 例外なく L4 install まで通る
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_provider_null_trace_recorder_raises_exception(self) -> None:
        """provider 自体が raise するケースでも本体は止まらない。"""
        def boom() -> object:
            raise RuntimeError("recorder broken")

        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=boom,
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_returns_null_trace_recorder_fallback_provider_none_even_if(self) -> None:
        """lazy lookup で recorder 未確定の場合 (provider が None を返す) でも emit する。"""
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: None,
        )
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        assert len(mem._mid_generations(_PID.value)) == 1

    def test_setter_via(self) -> None:
        """set_trace_recorder_provider(None) で no-op に戻しても emit は安全。"""
        rec = _RecordingRecorder()
        mem = RollingSummaryShortTermMemory(
            summary_service=None,
            trace_recorder_provider=lambda: rec,
        )
        mem.set_trace_recorder_provider(None)  # ← None で解除
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"o{i}", seq=i))
        # rec には record されないが、本体は動く
        assert len([e for e in rec.events if e["kind"] == "short_term_summary_generated"]) == 0
        assert len(mem._mid_generations(_PID.value)) == 1


class TestGetOldestEntryDatetimeMixedTimezones:
    """raw queue に naive と aware の datetime が混在しても crash しない。

    本来 ObservationEntry の occurred_at は upstream で aware に揃えられる
    建前だが、シナリオファイル由来の observation や snapshot 再生経路で
    naive な datetime が混入してくることがある。ここで min() が
    ``TypeError: can't compare offset-naive and offset-aware datetimes`` で
    落ちると、その tick 以降の prompt 構築が全て失敗し、実験が落ちる。
    そのため raw 内で混在していても UTC として揃えて比較する。
    """

    def _obs_at(self, prose: str, occurred_at: datetime) -> ObservationEntry:
        return ObservationEntry(
            occurred_at=occurred_at,
            output=ObservationOutput(prose=prose, structured={}),
        )

    def test_returns_oldest_when_naive_and_aware_entries_are_mixed(self) -> None:
        """naive datetime と aware datetime が混在しても crash せず、
        UTC として比較した最古を返す。"""
        mem = RollingSummaryShortTermMemory(summary_service=None)
        # naive (= 古い): 2026-06-01 00:00 (UTC 相当)
        mem.append(_PID, self._obs_at("old_naive", datetime(2026, 6, 1)))
        # aware (= 新しい): 2026-06-01 12:00 UTC
        mem.append(
            _PID,
            self._obs_at(
                "newer_aware", datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
            ),
        )
        oldest = mem.get_oldest_entry_datetime(_PID)
        assert oldest is not None
        # UTC として比較した最古 (= naive 側を UTC 扱いした 06-01 00:00)
        assert oldest.replace(tzinfo=None) == datetime(2026, 6, 1)
