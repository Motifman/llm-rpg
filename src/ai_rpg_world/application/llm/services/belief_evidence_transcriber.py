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

# U4 (予測誤差統一設計 部品3): attribution + CONFIRMATION

呼び出し側が ``in_context_belief_ids`` / ``had_expected_result`` を渡すことで
2 つの追加挙動が生まれる:

- PREDICTION_ERROR evidence に、その場面で in-context だった belief_id 群を
  添付する (固着パスの shortlist に必ず載せるための下ごしらえ)
- ``prediction_error`` が None (予測どおり) でも、in-context belief があり
  かつそのターンに ``expected_result`` を伴う行動があった (= 実際に何かを
  予測して行動した) 場合は CONFIRMATION evidence を積む

**flag ゲート**: 本クラス自身は ``BELIEF_ATTRIBUTION_ENABLED`` を知らない。
呼び出し側 (``EpisodicChunkCoordinator`` / スケジューラ群) が flag OFF のとき
常に ``in_context_belief_ids=()`` / ``had_expected_result=False`` を渡すことで
「導入前と挙動が一致する」を保証する (= 「配線と有効化の分離」パターンを
ここでも踏襲。呼び出し側だけが flag の値を知っていればよい)。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence, Tuple
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


def compute_chunk_attribution(
    action_results: Sequence[object],
) -> Tuple[Tuple[str, ...], bool]:
    """chunk を構成する action 群から attribution 用の 2 値を計算する (U4)。

    - in_context_belief_ids: 各 action の ``in_context_belief_ids`` の和集合
      (登場順・重複排除)
    - had_expected_result: いずれかの action が ``expected_result`` を
      持つか (= 「世界に対して何かを予測して行動した」ターンだったかの近似)

    呼び出し元 (``EpisodicChunkCoordinator`` / scheduler 群) が
    ``ChunkEncodingInput.action_results`` (``ActionResultEntry`` の tuple) を
    渡す想定。``getattr`` ベースで読むのは、テストで単純な duck-type オブジェクト
    を渡せるようにするため (既存の transcriber テストの慣習に合わせる)。
    """
    belief_ids: list[str] = []
    seen: set[str] = set()
    had_expected_result = False
    for action in action_results:
        for bid in getattr(action, "in_context_belief_ids", ()) or ():
            if bid not in seen:
                seen.add(bid)
                belief_ids.append(bid)
        if getattr(action, "expected_result", None):
            had_expected_result = True
    return tuple(belief_ids), had_expected_result


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
        self,
        being_id: BeingId,
        episode: SubjectiveEpisode,
        *,
        in_context_belief_ids: Tuple[str, ...] = (),
        had_expected_result: bool = False,
    ) -> Optional[BeliefEvidence]:
        """``episode.prediction_error`` の有無で PREDICTION_ERROR / CONFIRMATION
        のいずれかの evidence を積む (U4)。

        - ``prediction_error`` が非 None: PREDICTION_ERROR evidence を積む。
          ``in_context_belief_ids`` を添付する (空でも OK。U4 flag OFF 時は
          呼び出し側が常に空タプルを渡す設計)
        - ``prediction_error`` が None かつ ``in_context_belief_ids`` が非空
          かつ ``had_expected_result`` が True: 「信じて行動して当たった」
          CONFIRMATION evidence を積む。in-context belief が無い、または
          何も予測せず行動しただけのターンでは積まない (水増しガード)
        - それ以外: 何もしない

        積んだ evidence を返す (テストの assert 用。何も積まなければ None)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if not isinstance(in_context_belief_ids, tuple):
            raise TypeError("in_context_belief_ids must be tuple[str, ...]")
        if not isinstance(had_expected_result, bool):
            raise TypeError("had_expected_result must be bool")

        if episode.prediction_error is not None:
            evidence = BeliefEvidence(
                evidence_id=f"belief-evidence-{uuid4().hex}",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
                episode_ids=(episode.episode_id,),
                cue_signature=build_belief_evidence_cue_signature(episode),
                text=episode.prediction_error,
                # U6 (予測誤差統一設計 / salience): chunk 主観補完 LLM が付けた
                # episode.salience ("low"/"high") をそのまま転記する。
                # SALIENCE_STRUCTURED_FAILURE_ENABLED が OFF のときは
                # episode.salience が常に "low" のままなので、本行の挙動は
                # 導入前 (BELIEF_EVIDENCE_SALIENCE_LOW 固定) と一致する。
                salience=episode.salience,
                occurred_at=episode.occurred_at,
                tick=self._resolve_tick(),
                in_context_belief_ids=in_context_belief_ids,
            )
            self._buffer_store.append_by_being(being_id, evidence)
            self._emit_trace(being_id, evidence)
            return evidence

        if in_context_belief_ids and had_expected_result:
            confirmed_text = episode.expected or "行動の予測が当たった"
            evidence = BeliefEvidence(
                evidence_id=f"belief-evidence-{uuid4().hex}",
                source_kind=BeliefEvidenceSourceKind.CONFIRMATION,
                episode_ids=(episode.episode_id,),
                cue_signature=build_belief_evidence_cue_signature(episode),
                text=f"予測が当たった: {confirmed_text}",
                # CONFIRMATION は「一撃学習」の対象ではない (的中は反復して
                # こそ意味がある) ため常に low 固定。salience=high は
                # PREDICTION_ERROR 側 (chunk 補完 LLM の判定) にのみ許す。
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=episode.occurred_at,
                tick=self._resolve_tick(),
                in_context_belief_ids=in_context_belief_ids,
            )
            self._buffer_store.append_by_being(being_id, evidence)
            self._emit_trace(being_id, evidence)
            return evidence

        return None

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
                in_context_belief_ids=list(evidence.in_context_belief_ids),
            )
        except Exception:
            # trace 失敗で転記本体を止めない方針 (chunk 書き込みトレースと同じ)。
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE; skipping",
                exc_info=True,
            )


__all__ = ["BeliefEvidenceTranscriber"]
