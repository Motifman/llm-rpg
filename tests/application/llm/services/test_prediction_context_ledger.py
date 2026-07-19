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

    def test_returns_first_issue_discarded_id(self) -> None:
        """初回 issue は discarded なしで新しい id を返す。"""
        ledger = PredictionContextLedger()
        result = ledger.issue(PlayerId(1))
        assert result.prediction_context_id.startswith("predctx-")
        assert result.discarded is None

    def test_same_player_consume_issue_before_discarded(
        self,
    ) -> None:
        """同一 player で consume されないまま issue すると前回分が discarded になる。"""
        ledger = PredictionContextLedger()
        first = ledger.issue(PlayerId(1))
        second = ledger.issue(PlayerId(1))
        assert second.discarded is not None
        assert second.discarded.prediction_context_id == first.prediction_context_id
        assert second.prediction_context_id != first.prediction_context_id

    def test_consume_after_issue_discarded(self) -> None:
        """consume 済みの後の issue は discarded なし。"""
        ledger = PredictionContextLedger()
        ledger.issue(PlayerId(1))
        ledger.consume(PlayerId(1))
        second = ledger.issue(PlayerId(1))
        assert second.discarded is None

    def test_preserves_issue_episode_ids_belief_ids_context(self) -> None:
        """issue は episode ids belief ids を context に保持する。"""
        ledger = PredictionContextLedger()
        ledger.issue(
            PlayerId(1), episode_ids=("ep-1", "ep-2"), belief_ids=("belief-1",)
        )
        pending = ledger.peek(PlayerId(1))
        assert pending.episode_ids == ("ep-1", "ep-2")
        assert pending.belief_ids == ("belief-1",)

    def test_player_issue_does_not_affect(self) -> None:
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


class TestAttach:
    """二段階発行の 2 段目: 発行済み id に in-context 集合を後付けする。"""

    def test_pending_id_matches_episode_belief_ids_after(self) -> None:
        """pending id と一致すれば episode belief ids が後付けされる。"""
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        ledger.attach(
            PlayerId(1),
            issued.prediction_context_id,
            episode_ids=("ep-1", "ep-2"),
            belief_ids=("belief-1",),
        )
        pending = ledger.peek(PlayerId(1))
        assert pending.prediction_context_id == issued.prediction_context_id
        assert pending.episode_ids == ("ep-1", "ep-2")
        assert pending.belief_ids == ("belief-1",)

    def test_attach_after_consume_same_context_can_get(self) -> None:
        """attach 後も consume で同じ context が取れる。"""
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        ledger.attach(PlayerId(1), issued.prediction_context_id, episode_ids=("ep-1",))
        consumed = ledger.consume(PlayerId(1))
        assert consumed.prediction_context_id == issued.prediction_context_id
        assert consumed.episode_ids == ("ep-1",)

    def test_id_pending_matches_op(self) -> None:
        """途中で再発行された等の想定外状態では静かに諦める (混線防止)。"""
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        ledger.attach(PlayerId(1), "predctx-stale", episode_ids=("ep-1",))
        pending = ledger.peek(PlayerId(1))
        # 現行 pending は変化せず、in-context 集合も空のまま
        assert pending.prediction_context_id == issued.prediction_context_id
        assert pending.episode_ids == ()

    def test_pending_player_attach_op(self) -> None:
        """pending が無い player への attach は no op。"""
        ledger = PredictionContextLedger()
        ledger.attach(PlayerId(1), "predctx-x", episode_ids=("ep-1",))
        assert ledger.peek(PlayerId(1)) is None


class TestConsume:
    """consume() が pending context を取り出し ledger から取り除く挙動。"""

    def test_consume_pending_ledger(self) -> None:
        """consume は pending を返し ledger から取り除く。"""
        ledger = PredictionContextLedger()
        issued = ledger.issue(PlayerId(1))
        consumed = ledger.consume(PlayerId(1))
        assert consumed is not None
        assert consumed.prediction_context_id == issued.prediction_context_id
        assert ledger.peek(PlayerId(1)) is None

    def test_pending_player_consume_none(self) -> None:
        """pending が無い player の consume は None。"""
        ledger = PredictionContextLedger()
        assert ledger.consume(PlayerId(1)) is None

    def test_consume_two_none(self) -> None:
        """例外経路で record が 2 回走っても混線しない (2 回目は空を返すだけ)。"""
        ledger = PredictionContextLedger()
        ledger.issue(PlayerId(1))
        ledger.consume(PlayerId(1))
        assert ledger.consume(PlayerId(1)) is None
