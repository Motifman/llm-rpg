"""PredictionContextLedger (U1): prediction_context_id の発行・消費・寿命の単体テスト。

id の寿命 (実装計画 §U1 の不変条件): 「prompt build 時に発行し、次の
ActionResultRecorder.record が consume する。consume されず次の build が来たら
破棄」を、prompt_builder / ActionResultRecorder を経由せず ledger 単体で保証する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContext,
    PredictionContextLedger,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestIssue:
    """issue() が新しい id を発行し、直近未消費分を破棄として返す挙動。"""

    def test_初回_issue_は_discarded_なしで新しい_id_を返す(self) -> None:
        ledger = PredictionContextLedger()
        result = ledger.issue(PlayerId(1))
        assert result.prediction_context_id.startswith("predctx-")
        assert result.discarded is None

    def test_同一_player_で_consume_されないまま_issue_すると前回分が_discarded_になる(
        self,
    ) -> None:
        ledger = PredictionContextLedger()
        first = ledger.issue(PlayerId(1))
        second = ledger.issue(PlayerId(1))
        assert second.discarded is not None
        assert second.discarded.prediction_context_id == first.prediction_context_id
        assert second.prediction_context_id != first.prediction_context_id

    def test_consume_済みの後の_issue_は_discarded_なし(self) -> None:
        ledger = PredictionContextLedger()
        ledger.issue(PlayerId(1))
        ledger.consume(PlayerId(1))
        second = ledger.issue(PlayerId(1))
        assert second.discarded is None

    def test_issue_は_episode_ids_belief_ids_を_context_に保持する(self) -> None:
        ledger = PredictionContextLedger()
        ledger.issue(
            PlayerId(1), episode_ids=("ep-1", "ep-2"), belief_ids=("belief-1",)
        )
        pending = ledger.peek(PlayerId(1))
        assert pending.episode_ids == ("ep-1", "ep-2")
        assert pending.belief_ids == ("belief-1",)

    def test_player_をまたいだ_issue_は互いに影響しない(self) -> None:
        """player 間の混線防止: player_id をキーにした dict 構造で保証する。"""
        ledger = PredictionContextLedger()
        p1_result = ledger.issue(PlayerId(1))
        p2_result = ledger.issue(PlayerId(2))
        assert p2_result.discarded is None
        assert ledger.peek(PlayerId(1)).prediction_context_id == (
            p1_result.prediction_context_id
        )
        assert ledger.peek(PlayerId(2)).prediction_context_id == (
            p2_result.prediction_context_id
        )


class TestConsume:
    """consume() が pending context を取り出し ledger から取り除く挙動。"""

    def test_consume_は_pending_を返し_ledger_から取り除く(self) -> None:
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        consumed = ledger.consume(PlayerId(1))
        assert consumed is not None
        assert consumed.prediction_context_id == issued.prediction_context_id
        assert ledger.peek(PlayerId(1)) is None

    def test_pending_が無い_player_の_consume_は_None(self) -> None:
        ledger = PredictionContextLedger()
        assert ledger.consume(PlayerId(1)) is None

    def test_二重_consume_は_2回目が_None(self) -> None:
        """例外経路で record が 2 回走っても混線しない (2 回目は空を返すだけ)。"""
        ledger = PredictionContextLedger()
        ledger.issue(PlayerId(1))
        ledger.consume(PlayerId(1))
        assert ledger.consume(PlayerId(1)) is None
