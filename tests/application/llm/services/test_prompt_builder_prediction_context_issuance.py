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


class TestBeginPredictionContext:
    """ledger 未注入 / 注入時の 1 段目発行・破棄・NOTE emission。"""

    def test_returns_none_ledger_uninjected(self) -> None:
        """ledger 未注入なら None を返す。"""
        builder = _bare_builder(ledger=None)
        assert builder._begin_prediction_context(PlayerId(1)) is None

    def test_ledger_id_string_pending_empty_context(
        self,
    ) -> None:
        """1 段目は id だけ発行する。in-context 集合は attach まで空。"""
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger)
        result = builder._begin_prediction_context(PlayerId(1))
        assert result is not None
        assert result.startswith("predctx-")
        pending = ledger.peek(PlayerId(1))
        assert pending.prediction_context_id == result
        assert pending.episode_ids == ()
        assert pending.belief_ids == ()

    def test_build_note_trace_rendered(self) -> None:
        """未消費のまま次の build で破棄されると NOTE trace が出る。"""
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder, tick=7)

        first_id = builder._begin_prediction_context(PlayerId(1))
        # consume されないまま 2 回目の build (= no-tool ターン / 例外経路 相当)
        second_id = builder._begin_prediction_context(PlayerId(1))

        assert first_id != second_id
        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert len(notes) == 1
        assert notes[0].player_id == 1
        assert notes[0].tick == 7
        assert notes[0].payload["discarded_prediction_context_id"] == first_id

    def test_consume_build_note_not_rendered(self) -> None:
        """consume 済みなら 次の build で NOTE は出ない。"""
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder)

        builder._begin_prediction_context(PlayerId(1))
        ledger.consume(PlayerId(1))
        builder._begin_prediction_context(PlayerId(1))

        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert notes == []

    def test_recorder_uninjected_note_not_rendered(self) -> None:
        """trace 機構が無くても id の破棄自体 (ledger の状態遷移) は起きる。"""
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger, recorder=None)

        builder._begin_prediction_context(PlayerId(1))
        second_id = builder._begin_prediction_context(PlayerId(1))
        # 例外なく完走し、ledger には最新分だけが残る
        assert ledger.peek(PlayerId(1)).prediction_context_id == second_id

    def test_other_player_build_does_not_affect(self) -> None:
        """player をまたいだ混線防止 (ledger のキー分離を builder 経由でも確認)。"""
        ledger = PredictionContextLedger()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = _bare_builder(ledger=ledger, recorder=recorder)

        builder._begin_prediction_context(PlayerId(1))
        builder._begin_prediction_context(PlayerId(2))

        notes = [e for e in captured if e.kind == TraceEventKind.NOTE]
        assert notes == []


class TestAttachPredictionContext:
    """2 段目: 発行済み id に in-context 集合 (episode_ids / belief_ids) を後付け。"""

    def test_begin_line_id_context_after(self) -> None:
        """begin で発行した id に in context 集合が後付けされる。"""
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger)
        pid = builder._begin_prediction_context(PlayerId(1))
        builder._attach_prediction_context(
            player_id=PlayerId(1),
            prediction_context_id=pid,
            episode_ids=("ep-1", "ep-2"),
            belief_ids=("belief-1",),
        )
        pending = ledger.peek(PlayerId(1))
        assert pending.prediction_context_id == pid
        assert pending.episode_ids == ("ep-1", "ep-2")
        assert pending.belief_ids == ("belief-1",)

    def test_ledger_uninjected_op(self) -> None:
        """ledger 未注入なら no op。"""
        builder = _bare_builder(ledger=None)
        # 例外なく完走する (何も起きない)
        builder._attach_prediction_context(
            player_id=PlayerId(1),
            prediction_context_id=None,
            episode_ids=("ep-1",),
            belief_ids=(),
        )

    def test_id_none_op(self) -> None:
        """id None なら no op。"""
        ledger = PredictionContextLedger()
        builder = _bare_builder(ledger=ledger)
        builder._attach_prediction_context(
            player_id=PlayerId(1),
            prediction_context_id=None,
            episode_ids=("ep-1",),
            belief_ids=(),
        )
        assert ledger.peek(PlayerId(1)) is None
