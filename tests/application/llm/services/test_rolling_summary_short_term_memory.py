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

from ai_rpg_world.application.llm.contracts.short_term_memory import L4MidSummary
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
    DEFAULT_L1_SOFT_CAP,
    RollingSummaryShortTermMemory,
    format_mid_summary_block,
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

    def test_append_すると_get_recent_に_新しい順で_出る(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p1", seq=1))
        mem.append(_PID, _obs("p2", seq=2))
        recent = mem.get_recent(_PID, limit=10)
        proses = [o.output.prose for o in recent]
        assert proses == ["p2", "p1"]

    def test_append_all_は_順番に_append_する(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        evicted = mem.append_all(_PID, [_obs("p1", seq=1), _obs("p2", seq=2)])
        # rolling 実装は evict せず L4 に畳むので overflow は空
        assert evicted == []
        assert len(mem.get_recent(_PID, limit=10)) == 2

    def test_get_recent_の_limit_が_0以下_は_空list(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        mem.append(_PID, _obs("p", seq=1))
        assert mem.get_recent(_PID, limit=0) == []
        assert mem.get_recent(_PID, limit=-1) == []

    def test_未_append_な_player_は_空_list(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        assert mem.get_recent(_PID, limit=10) == []
        assert mem.get_mid_summary_text(_PID) == ""


# ──────────────────────────────────────────────────────────────────
# Trigger and generation
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryTrigger:
    """soft cap (15) 到達で L4 生成 trigger が発火する。"""

    def test_15件未満なら_L4_は_生成されない(self) -> None:
        stub = _StubSummaryService.make(
            result=_ParsedSummary(compressed_activity="ok", emotional_summary="", unresolved=())
        )
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP - 1):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        assert stub.call_count == 0
        assert mem._mid_generations(_PID.value) == []
        assert mem._raw_queue_len(_PID.value) == DEFAULT_L1_SOFT_CAP - 1

    def test_15件目で_L4_を_生成し_L1_を_減らす(self) -> None:
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

    def test_L4_は_3世代までで_最古を破棄(self) -> None:
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

    def test_L4_は_新しい順に_append_left_される(self) -> None:
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

    def test_15件超えると_template_fallback_で_L4_を_生やす(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        for i in range(DEFAULT_L1_SOFT_CAP + 5):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        # service=None でも 15 件超は template fallback で L4 を作る
        assert len(gens) >= 1
        assert all(g.is_fallback for g in gens)


class TestRollingSummaryLLMFailure:
    """LLM 失敗時は template fallback + warning ログを出す。"""

    def test_LLM_例外なら_template_fallback_に_縮退(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_LLM_の_ValueError_でも_fallback(self) -> None:
        stub = _StubSummaryService.make(exc=ValueError("parse failed"))
        mem = RollingSummaryShortTermMemory(summary_service=stub)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _obs(f"p{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        assert gens[0].is_fallback is True

    def test_hard_cap_到達時は_LLM_を_skip_して_強制_fallback(
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

    def test_L4_が_空なら_空文字(self) -> None:
        mem = RollingSummaryShortTermMemory(summary_service=None)
        assert mem.get_mid_summary_text(_PID) == ""

    def test_最新世代が_先頭で_出る(self) -> None:
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

    def test_resolver_の_例外は_default_に_縮退する(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_resolver_未指定なら_default_の_player_X_名で_動く(self) -> None:
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

    def test_soft_cap_が_0以下なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="l1_soft_cap"):
            RollingSummaryShortTermMemory(l1_soft_cap=0)

    def test_hard_cap_が_soft_未満なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="l1_hard_cap"):
            RollingSummaryShortTermMemory(l1_soft_cap=15, l1_hard_cap=10)

    def test_keep_generations_が_0以下なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="l4_keep_generations"):
            RollingSummaryShortTermMemory(l4_keep_generations=0)

    def test_service_が_非_ShortTermMemorySummaryService_なら_type_error(self) -> None:
        with pytest.raises(TypeError, match="summary_service"):
            RollingSummaryShortTermMemory(summary_service="not-a-service")  # type: ignore[arg-type]

    def test_persona_resolver_が_callable_でなければ_type_error(self) -> None:
        with pytest.raises(TypeError, match="persona_resolver"):
            RollingSummaryShortTermMemory(persona_resolver="not-callable")  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────
# format_mid_summary_block
# ──────────────────────────────────────────────────────────────────


class TestFormatMidSummaryBlock:
    """prompt 用の text 整形。"""

    def test_空_input_は_空文字(self) -> None:
        assert format_mid_summary_block([]) == ""

    def test_先頭世代に_最新_ラベルが_付く(self) -> None:
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

    def test_emotional_summary_と_unresolved_が_空なら_該当行が_出ない(self) -> None:
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
