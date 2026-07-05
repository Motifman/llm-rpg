"""BeliefEvidenceTranscriber — chunk 主観補完完了点でのルールベース転記。

U2 (証拠台帳統一設計 §2 U2): 「証拠の入口はすべてルールベースの転記
(新規 LLM 呼び出しなし)」に従う。PREDICTION_ERROR の判定自体は既存の
chunk 主観補完 LLM (``EpisodicChunkSubjectiveFieldsService``) が唯一の
source であり、本クラスは ``episode.prediction_error`` が非 None かどうか
を見るだけ (文字列一致カウンタ等の独自判定は作らない)。

呼び出し元は 2 経路 (同期 / 非同期) あるが、いずれも「chunk 主観補完 LLM が
episode を merge し終えた直後」という同じタイミングで
``record_if_applicable`` を呼ぶ。呼び出し元が既に being_id を解決済みの
文脈で呼ばれる前提とし、本クラス自身は being 解決ロジックを持たない
(= ``EpisodicChunkCoordinator._put_episode`` /
``*EpisodicSubjectiveScheduler._put_episode`` の解決結果をそのまま渡す)。

feature flag (``BELIEF_EVIDENCE_ENABLED``, default OFF) は「配線 (wire) と
有効化 (enable) の分離」の既存パターンに従い、wiring 層が本クラスを
注入するかどうかで制御する。呼び出し側 (coordinator / scheduler) は
``belief_evidence_transcriber is None`` を見るだけで済み、flag の値そのもの
を知らなくてよい。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from uuid import uuid4

from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    build_belief_evidence_cue_signature,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
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


class BeliefEvidenceTranscriber:
    """episode の ``prediction_error`` を ``BeliefEvidence`` に転記する。"""

    def __init__(
        self,
        buffer_store: BeliefEvidenceBufferRepository,
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
        if trace_recorder_provider is not None and not callable(
            trace_recorder_provider
        ):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(
            current_tick_provider
        ):
            raise TypeError("current_tick_provider must be callable or None")
        self._buffer_store = buffer_store
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def record_if_applicable(
        self, being_id: BeingId, episode: SubjectiveEpisode
    ) -> Optional[BeliefEvidence]:
        """``episode.prediction_error`` が非 None なら evidence を 1 件積む。

        None なら何もしない (= 転記条件はここだけ。新しい判定基準は
        追加しない)。積んだ evidence を返す (テストの assert 用)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")

        if episode.prediction_error is None:
            return None

        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
            episode_ids=(episode.episode_id,),
            cue_signature=build_belief_evidence_cue_signature(episode),
            text=episode.prediction_error,
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=episode.occurred_at,
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence)
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
            # trace 失敗で転記本体を止めない方針 (chunk 書き込みトレースと同じ)。
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE; skipping",
                exc_info=True,
            )


__all__ = ["BeliefEvidenceTranscriber"]
