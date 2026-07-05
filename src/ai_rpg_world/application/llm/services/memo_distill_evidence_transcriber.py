"""MemoDistillEvidenceTranscriber — memo_done 完了点でのルールベース転記。

U5 (予測誤差統一設計 §2 U5 / semantic_learning_consolidation_design.md
「証拠の入口」表の MEMO_DISTILL 行): memo が完了 (``memo_done``) したとき、
その memo 本文 + ``MemoFulfillmentContext`` を**無条件で** ``BeliefEvidence``
に転記する。ノイズ (一般化不能なタスクメモ) か持続知識 (S6: 「岩礁海岸は
山方面に通じず×」のような学び) かはここでは判定しない。判定は固着パスの
``BeliefConsolidationCoordinator`` の LLM が discard / create として行う
(U3b で実装済み)。本クラスは新しい判定基準を追加しない (= 証拠の入口は
すべてルールベースの転記、新規 LLM 呼び出しなしという U2 以来の方針を踏襲)。

``BeliefEvidence.episode_ids`` は必須 (traceability) のため、その being の
**直近の episode** に anchor する。episode が 1 件も無ければ証拠を作らず
skip する (``StructuredFailureEvidenceTranscriber`` と同じ設計判断: 証拠を
捏造してでも残すより、無ければ諦める。warning ログで可視化する)。

memo_done は one-shot (memo は完了と同時に消費され、二度と同じ memo が
``memo_done`` を通ることはない) なので、discard 済み memo の再判定防止用の
専用 store は持たない。同じ memo 本文がもう一度 evidence 化されることは
構造上ありえない。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from uuid import uuid4

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

_logger = logging.getLogger(__name__)

# memo は tool/spot のような固定 cue を持たないため、cue_signature は決定論の
# 固定キーにする。固着パスの LLM は text (memo 本文 + fulfillment_context) を
# 読んで discard / create を判定するので、shortlist の cue 一致にはあまり
# 依存しない (STRUCTURED_FAILURE の "tool:<tool_name>" とは事情が異なる)。
MEMO_DISTILL_CUE_SIGNATURE = "self:memo"

# text が肥大化すると固着パスの prompt を圧迫するため上限で truncate する。
# memo 本文自体は短い想定 (LLM が memo_add で書く 1〜2 文) だが、
# fulfillment_context (直近観測 5 件 + 直近行動 5 件) を結合すると長くなり
# 得るため安全マージンを取る。
_MEMO_DISTILL_TEXT_MAX_CHARS = 1200


class MemoDistillEvidenceTranscriber:
    """``memo_done`` を ``BeliefEvidence`` (MEMO_DISTILL) に転記する。"""

    def __init__(
        self,
        buffer_store: BeliefEvidenceBufferRepository,
        episode_store: EpisodicEpisodeRepository,
        *,
        trace_recorder_provider: Optional[
            Callable[[], Optional[ITraceRecorder]]
        ] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if not isinstance(buffer_store, BeliefEvidenceBufferRepository):
            raise TypeError(
                "buffer_store must be BeliefEvidenceBufferRepository"
            )
        if not isinstance(episode_store, EpisodicEpisodeRepository):
            raise TypeError("episode_store must be EpisodicEpisodeRepository")
        if trace_recorder_provider is not None and not callable(
            trace_recorder_provider
        ):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(
            current_tick_provider
        ):
            raise TypeError("current_tick_provider must be callable or None")
        self._buffer_store = buffer_store
        self._episode_store = episode_store
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def record_from_memo(
        self,
        being_id: BeingId,
        *,
        memo_content: str,
        fulfillment_context: Optional[MemoFulfillmentContext],
    ) -> Optional[BeliefEvidence]:
        """memo 本文を無条件で MEMO_DISTILL evidence に積む。

        being の直近 episode が無ければ evidence を作らず None を返す
        (warning ログつき skip)。ノイズかどうかの判定はしない (固着パスの
        LLM に委ねる)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(memo_content, str) or not memo_content.strip():
            raise TypeError("memo_content must be non-empty str")
        if fulfillment_context is not None and not isinstance(
            fulfillment_context, MemoFulfillmentContext
        ):
            raise TypeError(
                "fulfillment_context must be MemoFulfillmentContext or None"
            )

        recent = self._episode_store.list_recent_by_being(being_id, limit=1)
        if not recent:
            _logger.warning(
                "MemoDistillEvidenceTranscriber: no episode to anchor for "
                "being_id=%s; skipping evidence",
                being_id.value,
            )
            return None
        anchor_episode = recent[0]

        text = self._build_text(memo_content, fulfillment_context)

        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.MEMO_DISTILL,
            episode_ids=(anchor_episode.episode_id,),
            cue_signature=MEMO_DISTILL_CUE_SIGNATURE,
            text=text,
            # 一撃学習経路 (salience=high) は chunk 主観補完 LLM 専用に残す。
            # memo_done は反復も驚きの大小も持たないルールベースの転記
            # なので常に low。
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=anchor_episode.occurred_at,
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence)
        return evidence

    @staticmethod
    def _build_text(
        memo_content: str, fulfillment_context: Optional[MemoFulfillmentContext]
    ) -> str:
        parts = [memo_content.strip()]
        if fulfillment_context is not None:
            if fulfillment_context.recent_observation_proses:
                parts.append(
                    "直近の観測: "
                    + " / ".join(fulfillment_context.recent_observation_proses)
                )
            if fulfillment_context.recent_action_summaries:
                parts.append(
                    "直近の行動: "
                    + " / ".join(fulfillment_context.recent_action_summaries)
                )
        text = "\n".join(parts)
        return text[:_MEMO_DISTILL_TEXT_MAX_CHARS]

    def _resolve_tick(self) -> Optional[int]:
        if self._current_tick_provider is None:
            return None
        try:
            return self._current_tick_provider()
        except Exception:
            _logger.debug(
                "current_tick_provider raised; tick left as None",
                exc_info=True,
            )
            return None

    def _emit_trace(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        recorder: Optional[ITraceRecorder] = None
        if self._trace_recorder_provider is not None:
            try:
                recorder = self._trace_recorder_provider()
            except Exception:
                _logger.debug(
                    "trace_recorder_provider raised; skipping BELIEF_EVIDENCE trace",
                    exc_info=True,
                )
                recorder = None
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.BELIEF_EVIDENCE,
                tick=evidence.tick,
                being_id=being_id.value,
                evidence_id=evidence.evidence_id,
                source_kind=evidence.source_kind.value,
                episode_ids=list(evidence.episode_ids),
                cue_signature=evidence.cue_signature,
                text_snippet=evidence.text[:120],
                salience=evidence.salience,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE "
                "(memo_distill); skipping",
                exc_info=True,
            )


__all__ = ["MemoDistillEvidenceTranscriber", "MEMO_DISTILL_CUE_SIGNATURE"]
