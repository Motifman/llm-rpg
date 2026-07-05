"""DefaultPromptBuilder._issue_prediction_context_id (U1) の単体テスト。

build() 全体を組み立てずに、id 発行ロジックだけを ``object.__new__`` +
最小限の属性注入で検証する (``TestPromptBuilderRecallTraceEmission`` と同じ
パターン)。プロンプト全体の組み立てを経由しないことで、依存が重い
core services のモック化を避ける。
"""

from __future__ import annotations

from typing import List

import pytest

from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContextLedger,
)
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture_trace(recorder: NullTraceRecorder) -> List:
    captured: List = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


def _bare_builder(*, ledger, recorder=None, tick: int = 0) -> DefaultPromptBuilder:
    builder = object.__new__(DefaultPromptBuilder)
    builder._prediction_context_ledger = ledger
    builder._trace_recorder = recorder
    builder._trace_recorder_provider = None
    builder._current_tick_provider = lambda: tick
    import logging

    builder._logger = logging.getLogger("test")
    return builder


class TestIssuePredictionContextId:
    """ledger 未注入 / 注入時の発行・破棄・NOTE emission。"""

    def test_ledger_未注入なら_None_を返す(self) -> None:
        builder = _bare_builder(ledger=None)
        result = builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        assert result is None

    def test_ledger_注入時は_id_文字列を返す(self) -> None:
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger)
        result = builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=("ep-1",), belief_ids=("belief-1",)
        )
        assert result is not None
        assert result.startswith("predctx-")
        pending = ledger.peek(PlayerId(1))
        assert pending.episode_ids == ("ep-1",)
        assert pending.belief_ids == ("belief-1",)

    def test_未消費のまま次の_build_で破棄されると_NOTE_trace_が出る(self) -> None:
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder, tick=7)

        first_id = builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        # consume されないまま 2 回目の build (= no-tool ターン / 例外経路 相当)
        second_id = builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )

        assert first_id != second_id
        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert len(notes) == 1
        assert notes[0].player_id == 1
        assert notes[0].tick == 7
        assert notes[0].payload["discarded_prediction_context_id"] == first_id

    def test_consume_済みなら_次の_build_で_NOTE_は出ない(self) -> None:
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder)

        builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        ledger.consume(PlayerId(1))
        builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )

        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert notes == []

    def test_recorder_未注入でも破棄は起きるが_NOTE_は出ない(self) -> None:
        """trace 機構が無くても id の破棄自体 (ledger の状態遷移) は起きる。"""
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger, recorder=None)

        builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        second_id = builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        # 例外なく完走し、ledger には最新分だけが残る
        assert ledger.peek(PlayerId(1)).prediction_context_id == second_id

    def test_他プレイヤーの_build_は互いに影響しない(self) -> None:
        """player をまたいだ混線防止 (ledger のキー分離を builder 経由でも確認)。"""
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder)

        builder._issue_prediction_context_id(
            player_id=PlayerId(1), episode_ids=(), belief_ids=()
        )
        builder._issue_prediction_context_id(
            player_id=PlayerId(2), episode_ids=(), belief_ids=()
        )

        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert notes == []
