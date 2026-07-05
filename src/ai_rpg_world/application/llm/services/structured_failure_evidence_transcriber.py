"""StructuredFailureEvidenceTranscriber — loop_guard 発火点でのルールベース転記。

U6 (予測誤差統一設計 §2 U6 / semantic_learning_consolidation_design.md
「証拠の入口」表の STRUCTURED_FAILURE 行): 「同一 (tool, fingerprint,
error_code) の閾値反復」を ``ToolCallLoopGuardService`` の
cross_tick_failure トラッカーが検知したとき (= 呼び出し側が
``CrossTickFailureTrigger`` を受け取ったとき) に、``BeliefEvidence`` を
1 件積む。判定自体は既に loop_guard が行っており、本クラスは新しい判定
基準を追加しない (= 証拠の入口はすべてルールベースの転記、新規 LLM
呼び出しなしという U2 以来の方針を踏襲する)。

``BeliefEvidence.episode_ids`` は必須 (traceability) のため、その being の
**直近の episode** に anchor する。episode が 1 件も無い (chunk がまだ
書かれていない) ときは証拠を作らず skip する。これは「証拠を捏造してでも
残す」より「無ければ諦める」を選ぶ設計判断で、warning ログで可視化する
(静かに失われる方が悪い、というのが本プロジェクトの一貫した方針)。
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


class StructuredFailureEvidenceTranscriber:
    """loop_guard の cross_tick_failure 発火を ``BeliefEvidence`` に転記する。"""

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

    def record_if_triggered(
        self,
        being_id: BeingId,
        *,
        tool_name: str,
        error_code: str,
        count: int,
    ) -> Optional[BeliefEvidence]:
        """being の直近 episode に anchor して STRUCTURED_FAILURE evidence を積む。

        直近 episode が無ければ evidence を作らず None を返す (warning ログ
        つき skip)。呼び出し側 (``record_and_check`` が
        ``CrossTickFailureTrigger`` を返したとき) は「今回 loop_guard が
        新規に警告を発火した」ことを既に保証しているので、本メソッド側に
        重複判定は無い。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(tool_name, str) or not tool_name:
            raise TypeError("tool_name must be non-empty str")
        if not isinstance(error_code, str) or not error_code:
            raise TypeError("error_code must be non-empty str")
        if not isinstance(count, int):
            raise TypeError("count must be int")

        recent = self._episode_store.list_recent_by_being(being_id, limit=1)
        if not recent:
            _logger.warning(
                "StructuredFailureEvidenceTranscriber: no episode to anchor "
                "for being_id=%s tool_name=%s error_code=%s; skipping evidence",
                being_id.value,
                tool_name,
                error_code,
            )
            return None
        anchor_episode = recent[0]

        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.STRUCTURED_FAILURE,
            episode_ids=(anchor_episode.episode_id,),
            # U3b の shortlist と一致させるため tool 軸のみ (episode 由来の
            # spot/player は付けない。design 上「tool:<tool_name>」固定)。
            cue_signature=f"tool:{tool_name}",
            text=f"「{tool_name}」が「{error_code}」を{count}回反復した。",
            # 件数駆動 (cue_signature repeat) の早期 trigger は既に
            # BeliefConsolidationCoordinator 側の仕組みに任せるため、ここは
            # 常に low (salience=high の一撃学習経路は chunk 主観補完 LLM
            # 専用に残す)。
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=anchor_episode.occurred_at,
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence, count=count)
        return evidence

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

    def _emit_trace(
        self, being_id: BeingId, evidence: BeliefEvidence, *, count: int
    ) -> None:
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
                repeat_count=count,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE "
                "(structured_failure); skipping",
                exc_info=True,
            )


__all__ = ["StructuredFailureEvidenceTranscriber"]
