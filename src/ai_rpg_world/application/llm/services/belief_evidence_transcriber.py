"""BeliefEvidenceTranscriber — chunk 主観補完などの完了点でのルールベース転記。

U2 (証拠台帳統一設計 §2 U2): 「証拠の入口はすべてルールベースの転記
(新規 LLM 呼び出しなし)」に従う。本クラスは判定を作らず、既に下された判定
(約束の清算) を ``BeliefEvidence`` に写すだけ。

予測の当否は chunk の ``prediction_error`` からは積まない。確定した予期から積んで
いた受け取る側は #1631 で消した。

feature flag (``BELIEF_EVIDENCE_ENABLED``, default OFF) は「配線 (wire) と
有効化 (enable) の分離」の既存パターンに従い、wiring 層が本クラスを
注入するかどうかで制御する。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    build_belief_evidence_cue_signature,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PENDING_KIND_PLAN,
    PENDING_VERDICT_BROKEN,
    PENDING_VERDICT_FULFILLED,
    PendingPrediction,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

_logger = logging.getLogger(__name__)

def _pending_cue_signature(
    pending: PendingPrediction, episode: SubjectiveEpisode
) -> str:
    """約束の清算 evidence の cue_signature を決める (U10b)。

    人物 (``player:``) の約束は対象 player belief に寄せたいので player cue を
    優先。無ければ最初の resolution cue、それも無ければ episode 由来の
    署名にフォールバックする (resolution_cues は VO 制約で必ず 1 件以上ある
    ため通常は最初の cue が採られる)。
    """
    player_cue = next(
        (c for c in pending.resolution_cues if c.startswith("player:")), None
    )
    if player_cue is not None:
        return player_cue
    if pending.resolution_cues:
        return pending.resolution_cues[0]
    return build_belief_evidence_cue_signature(episode)


class BeliefEvidenceTranscriber:
    """既に下された判定を ``BeliefEvidence`` に転記する。"""

    def __init__(
        self,
        buffer_store: BeliefEvidenceBufferRepository,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None] | None = None,
        current_tick_provider: Callable[[], int | None] | None = None,
        memory_turn_reader: MemoryTurnReader,
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
        if not isinstance(memory_turn_reader, MemoryTurnReader):
            raise TypeError("memory_turn_reader must be MemoryTurnReader")
        self._current_tick_provider = current_tick_provider
        self._memory_turn_reader = memory_turn_reader

    def record_pending_resolution(
        self,
        being_id: BeingId,
        episode: SubjectiveEpisode,
        pending: PendingPrediction,
        *,
        verdict: str,
    ) -> BeliefEvidence | None:
        """再浮上していた約束の清算を ``PENDING_RESOLUTION`` evidence に転記する (U10b)。

        - ``verdict == "fulfilled"``: 「約束が果たされた」= 相手への信頼の支持。
          的中と同じく反復してこそ意味があるため salience=low。
        - ``verdict == "broken"``: 「約束が破られた」= 反証。裏切りは一撃で
          印象に残る出来事なので salience=high (即時固着候補) にする。

        P11: ``pending.kind`` が ``plan`` (自分の方針への見込み) のときは文面を
        「見込み『…』は当たった/外れた」に変える。破れは「方針レベルの予測誤差」
        として反証に流れ、有害な belief (「この探索は手がかりになる」型) を訂正
        できるようにするのが plan 予測化の狙い。salience は verdict 由来なので
        種別に依らず同じ (fulfilled=low / broken=high)。

        ``cue_signature`` は約束の ``resolution_cues`` のうち人物 (``player:``)
        を優先して採る (清算は「対象 player belief への支持/反証」なので、
        人物の belief クラスタに寄せる)。人物 cue が無ければ最初の cue を使う。
        判定 (fulfilled/broken) は既に chunk 主観補完 LLM が下しており、本
        メソッドは新しい判定基準を作らない (U2 以来の「証拠の入口は転記のみ」)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if not isinstance(pending, PendingPrediction):
            raise TypeError("pending must be PendingPrediction")
        if verdict not in (PENDING_VERDICT_FULFILLED, PENDING_VERDICT_BROKEN):
            raise ValueError(
                f"verdict must be one of "
                f"({PENDING_VERDICT_FULFILLED!r}, {PENDING_VERDICT_BROKEN!r}), "
                f"got {verdict!r}"
            )

        fulfilled = verdict == PENDING_VERDICT_FULFILLED
        if pending.kind == PENDING_KIND_PLAN:
            text = (
                f"見込み「{pending.text}」は当たった。"
                if fulfilled
                else f"見込み「{pending.text}」は外れた。"
            )
        else:
            text = (
                f"約束「{pending.text}」は果たされた。"
                if fulfilled
                else f"約束「{pending.text}」は破られた。"
            )
        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.PENDING_RESOLUTION,
            episode_ids=(episode.episode_id,),
            cue_signature=_pending_cue_signature(pending, episode),
            text=text,
            salience=(
                BELIEF_EVIDENCE_SALIENCE_LOW
                if fulfilled
                else BELIEF_EVIDENCE_SALIENCE_HIGH
            ),
            occurred_at=episode.occurred_at,
            observed_turn=self._memory_turn_reader.current_turn(being_id),
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence)
        return evidence

    def _resolve_tick(self) -> int | None:
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
        recorder: ITraceRecorder | None = None
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
                in_context_belief_ids=list(evidence.in_context_belief_ids),
                source_speaker=evidence.source_speaker,
            )
        except Exception:
            # trace 失敗で転記本体を止めない方針 (chunk 書き込みトレースと同じ)。
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE; skipping",
                exc_info=True,
            )


__all__ = ["BeliefEvidenceTranscriber"]
