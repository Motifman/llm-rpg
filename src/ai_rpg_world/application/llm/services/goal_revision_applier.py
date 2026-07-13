"""GoalRevisionApplier — LLM が書いた goal_update / goal_outcome を goal store に
反映する (P6 立て直し + P8 清算)。

goal_layer_design_active_inference.md §4 G2/G4 (2026-07-12 改訂): 目的の改訂・
清算は意識 (エージェント自身) が行う。``goal_update`` (立て直し) と
``goal_outcome`` (achieved / abandoned の清算) はどちらも全 world-action tool に
常時露出される optional フィールド (schema は tick 間不変) で、非 null のとき本
applier が goal store を更新する。**書き込みゲート (トリガターン限定) は無い** —
どのターンでも書ける。高度は schema 説明文の摩擦と journal 観測で守る。

組み合わせの意味論:
- ``goal_update`` のみ = 言い直し。旧目的を SUPERSEDED にして新目的へ (P6)
- ``goal_outcome`` + ``goal_update`` = 旧目的を achieved / abandoned で清算して
  次の目的へ (P8)
- ``goal_outcome`` のみ = 目的を閉じて無目的に戻る (【現在の目的】= 未定描画)

いずれも:
- 現在の active 目的が **locked** (シナリオ初期目的) への書き換え・清算は拒否し、
  観測で本人に返す (silent にしない)。シナリオ目的の達成はシナリオの終了条件が
  決める
- ``goal_update`` の文字数が入口の上限
  (``SELF_AUTHORED_GOAL_TEXT_MAX_CHARS``) を超えたときも拒否し、観測で本人に
  返す (HIGH-1 回帰対応: schema の maxLength は advisory なので、ここでも
  再検証する)
- 清算 (achieved / abandoned) が起きたら、その目的を「選好的な予測」の清算として
  belief evidence に転記し、``GOAL_RESOLUTION`` trace を残す (P8)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import uuid4

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.exception.goal_exception import (
    GoalUpdateTextTooLongException,
)
from ai_rpg_world.domain.memory.goal.repository.goal_journal_repository import (
    GoalJournalRepository,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ABANDONED,
    GOAL_STATUS_ACHIEVED,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
    validate_self_authored_goal_text,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

# locked 目的への書き換え・清算を拒否したとき本人に返す観測文 (§4 G2)。
GOAL_LOCKED_REJECTION_OBSERVATION = (
    "その目的は今は手放せない、と自分でも分かっている。"
)

# goal_update の文字数が入口の上限 (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS) を超えた
# とき本人に返す観測文 (HIGH-1 回帰対応)。schema の maxLength は advisory な
# ので、超過が実際に届いた場合も silent に捨てず observation で返す。
GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION = (
    "考えが長くなりすぎて、うまく一つの目的にまとめきれなかった。"
)

# goal_outcome enum → 清算後の goal status。
_OUTCOME_TO_STATUS = {
    "achieved": GOAL_STATUS_ACHIEVED,
    "abandoned": GOAL_STATUS_ABANDONED,
}

# LOW-3: GOAL_REVISION_REJECTED trace の attempted_goal_text 切り詰め長。
# validate_self_authored_goal_text で既に SELF_AUTHORED_GOAL_TEXT_MAX_CHARS
# (200) 以内には収まっているが、trace payload はさらに短い snippet で十分
# なので、他の FILLED trace の recall_text_snippet と同じ 120 に揃える。
_GOAL_REJECTION_TEXT_SNIPPET_MAX_CHARS = 120


class GoalRevisionApplier:
    """非 null の goal_update / goal_outcome を goal store に反映する。"""

    def __init__(
        self,
        goal_store: GoalJournalRepository,
        *,
        observation_sink: Callable[[PlayerId, str], None],
        current_tick_provider: Callable[[], int],
        now_provider: Callable[[], "object"],
        settlement_transcriber_provider: Optional[Callable[[], Optional[Any]]] = None,
        trace_recorder_provider: Optional[
            Callable[[], Optional[ITraceRecorder]]
        ] = None,
    ) -> None:
        if not isinstance(goal_store, GoalJournalRepository):
            raise TypeError("goal_store must be GoalJournalRepository")
        if not callable(observation_sink):
            raise TypeError("observation_sink must be callable")
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        if not callable(now_provider):
            raise TypeError("now_provider must be callable")
        if settlement_transcriber_provider is not None and not callable(
            settlement_transcriber_provider
        ):
            raise TypeError(
                "settlement_transcriber_provider must be callable or None"
            )
        if trace_recorder_provider is not None and not callable(
            trace_recorder_provider
        ):
            raise TypeError("trace_recorder_provider must be callable or None")
        self._goal_store = goal_store
        self._observation_sink = observation_sink
        self._current_tick_provider = current_tick_provider
        self._now_provider = now_provider
        self._settlement_transcriber_provider = settlement_transcriber_provider
        self._trace_recorder_provider = trace_recorder_provider

    def apply(
        self,
        being_id: BeingId,
        player_id: PlayerId,
        *,
        goal_update_text: Optional[str],
        goal_outcome: Optional[str],
    ) -> Optional[GoalEntry]:
        """goal_update / goal_outcome を反映する。反映後の active 目的を返す
        (清算のみで無目的に戻ったとき・何もしなかったときは None)。

        - どちらも None / 空: 何もしない (= 目的を変えない)
        - goal_update が入口の上限を超える: 拒否 + 観測 (schema の maxLength は
          advisory なので、ここでも再検証する。§4 G2)
        - active が locked: 拒否 + 観測 (清算も立て直しもしない)
        - goal_outcome あり + active あり: 清算 (achieved/abandoned) + 転記 + trace
        - goal_update あり: 清算後 / 言い直しで新目的を立てる
        """
        text = goal_update_text.strip() if isinstance(goal_update_text, str) else ""
        outcome_status = _OUTCOME_TO_STATUS.get(goal_outcome) if goal_outcome else None
        if not text and outcome_status is None:
            return None

        if text:
            try:
                validate_self_authored_goal_text(text)
            except GoalUpdateTextTooLongException:
                # store には触れず (何もしなかった no-op に畳む)、silent に
                # しない (本人に観測で返す)。
                self._observation_sink(
                    player_id, GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION
                )
                return None

        active = self._goal_store.get_active_by_being(being_id)
        if active is not None and active.locked:
            # locked への書き換え・清算はいずれも silent にしない。
            self._observation_sink(player_id, GOAL_LOCKED_REJECTION_OBSERVATION)
            # LOW-3: 本人への観測とは別に、run 分析で見直し試行 (拒否含む) の
            # 頻度を数えられるよう trace にも残す。
            self._emit_goal_revision_rejected_trace(
                being_id, active, attempted_goal_text=text or None
            )
            return None

        # 新目的があるなら **store を変更する前に** 構築して検証を済ませる。
        # 清算 (settle + 転記 + trace) を先に走らせてから GoalEntry 構築が例外を
        # 投げると、「旧目的は閉じたのに次の目的が立たない」部分コミットになる
        # (達成 evidence だけ残り本人の意図した後継目的が消える silent failure)。
        # 構築を先頭に置けば、不正な text はここで例外になり store は無傷 =
        # 何もしなかった no-op に畳まれる (P6 と同じ無害な挙動)。
        new_entry: Optional[GoalEntry] = None
        if text:
            new_entry = GoalEntry(
                goal_id=f"goal-{uuid4().hex}",
                player_id=int(player_id.value),
                text=text,
                status=GOAL_STATUS_ACTIVE,
                locked=False,
                origin=GOAL_ORIGIN_SELF,
                created_tick=self._resolve_tick(),
                created_at=self._now_provider(),
                supersedes=active.goal_id if active is not None else None,
            )

        settled = False
        if outcome_status is not None and active is not None:
            closed = self._goal_store.settle_by_being(
                being_id, goal_id=active.goal_id, outcome_status=outcome_status
            )
            if closed is not None:
                settled = True
                self._settle_side_effects(being_id, closed, outcome_status)

        if new_entry is None:
            # goal_outcome のみ (清算だけ) → 無目的に戻る。
            return None
        if active is not None and not settled:
            # 言い直し (清算なし) → 旧目的は SUPERSEDED。
            self._goal_store.supersede_by_being(
                being_id, old_goal_id=active.goal_id, new_entry=new_entry
            )
        else:
            # 清算済み (active は既に achieved/abandoned) or もともと active 無し。
            self._goal_store.add_by_being(being_id, new_entry)
        return new_entry

    def _settle_side_effects(
        self, being_id: BeingId, closed: GoalEntry, outcome_status: str
    ) -> None:
        """清算した目的を belief evidence に転記し GOAL_RESOLUTION trace を残す。

        転記 (belief evidence) は BELIEF 系 flag が OFF なら transcriber 未配線
        (provider が None を返す) で黙って skip する — 学習経路自体が OFF なので
        失われる学びは無い。trace は経路の有無に関わらず残す (目的の一生の観測点)。
        """
        evidence_id: Optional[str] = None
        transcriber = self._resolve_settlement_transcriber()
        if transcriber is not None:
            try:
                evidence = transcriber.record_goal_resolution(
                    being_id,
                    closed,
                    outcome=outcome_status,
                    occurred_at=self._now_provider(),
                )
                evidence_id = (
                    evidence.evidence_id if evidence is not None else None
                )
            except Exception:
                _logger.warning(
                    "record_goal_resolution failed (goal_id=%s); "
                    "goal は清算済み、evidence 転記だけ落ちた",
                    closed.goal_id,
                    exc_info=True,
                )
        self._emit_goal_resolution_trace(
            being_id, closed, outcome_status, evidence_id
        )

    def _resolve_settlement_transcriber(self) -> Optional[Any]:
        if self._settlement_transcriber_provider is None:
            return None
        try:
            return self._settlement_transcriber_provider()
        except Exception:
            _logger.debug(
                "settlement_transcriber_provider raised; skipping transcription",
                exc_info=True,
            )
            return None

    def _emit_goal_resolution_trace(
        self,
        being_id: BeingId,
        closed: GoalEntry,
        outcome_status: str,
        evidence_id: Optional[str],
    ) -> None:
        if self._trace_recorder_provider is None:
            return
        try:
            recorder = self._trace_recorder_provider()
        except Exception:
            _logger.debug(
                "trace_recorder_provider raised; skipping GOAL_RESOLUTION",
                exc_info=True,
            )
            return
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.GOAL_RESOLUTION,
                tick=self._resolve_tick(),
                being_id=str(being_id.value),
                goal_id=closed.goal_id,
                outcome=outcome_status,
                goal_text=closed.text,
                evidence_id=evidence_id,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for GOAL_RESOLUTION; skipping",
                exc_info=True,
            )

    def _emit_goal_revision_rejected_trace(
        self,
        being_id: BeingId,
        locked_active: GoalEntry,
        *,
        attempted_goal_text: Optional[str],
    ) -> None:
        """LOW-3: locked への書き換え・清算の拒否を trace に残す。

        本人への観測 (silent にしない) とは独立の観測点。trace_recorder
        未配線 / provider 例外 / record 自体の例外は全て黙って skip する
        (拒否自体の本人への通知は既に済んでおり、trace はあくまで run 分析
        用の付随情報)。
        """
        if self._trace_recorder_provider is None:
            return
        try:
            recorder = self._trace_recorder_provider()
        except Exception:
            _logger.debug(
                "trace_recorder_provider raised; skipping GOAL_REVISION_REJECTED",
                exc_info=True,
            )
            return
        if recorder is None:
            return
        snippet = (
            attempted_goal_text[:_GOAL_REJECTION_TEXT_SNIPPET_MAX_CHARS]
            if attempted_goal_text
            else None
        )
        try:
            recorder.record(
                TraceEventKind.GOAL_REVISION_REJECTED,
                tick=self._resolve_tick(),
                being_id=str(being_id.value),
                reason="locked",
                goal_id=locked_active.goal_id,
                attempted_goal_text=snippet,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for GOAL_REVISION_REJECTED; skipping",
                exc_info=True,
            )

    def _resolve_tick(self) -> int:
        try:
            tick = self._current_tick_provider()
        except Exception:
            _logger.debug("current_tick_provider raised; using 0", exc_info=True)
            return 0
        return tick if isinstance(tick, int) and not isinstance(tick, bool) else 0


__all__ = [
    "GoalRevisionApplier",
    "GOAL_LOCKED_REJECTION_OBSERVATION",
    "GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION",
]
