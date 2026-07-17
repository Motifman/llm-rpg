"""StateCollapseEvidenceTranscriber — 状態破綻の一次発生点での高 salience 転記。

PR-D (状態破綻を高 salience evidence として記憶化する):
3 run で一貫して観測された非対称を解消する。structured_failure evidence の
入口は ``tool_call_loop_guard`` (同一失敗の反復検出) のみで、「examine を
3 回失敗」は学習素材になるのに、「空腹 100 で戦闘不能になった」というエン
ジン上の確定事実は prose 観測 1 行しか残らず belief 形成の素材にならない
逆転があった (run 002: エイダが t60 に down して 140 tick 放置されたが誰の
belief にもならなかった)。

設計方針 (重要): これは知覚の増幅であって行動規則ではない。「倒れた」
「空腹が限界に達した」という確定事実を記憶システムに強く見せるだけで、
そこから何を学ぶか (「夜の森は危ない」なのか「空腹を放置したのが悪い」
なのか) の解釈は従来どおり LLM の belief 固着に委ねる。text は事実の記述
に留め、教訓や指示を含めない。判定自体は既にエンジン側の状態遷移
(is_down フラグ / hunger.value >= hunger.max_value) が行っており、本クラス
は新しい判定基準を追加しない (= 証拠の入口はすべてルールベースの転記、
新規 LLM 呼び出しなしという U2 以来の方針を踏襲する。
``StructuredFailureEvidenceTranscriber`` と同じ「転記のみ」分担)。

``StructuredFailureEvidenceTranscriber`` との違いは、発火元が「反復回数の
閾値」ではなく「状態遷移」であること。反復ではなく一度きりの遷移である
ため、同一事象の二重積みを防ぐ dedup 状態を本クラス自身が持つ (down /
hunger max それぞれ独立に、being 単位で「現在その状態が進行中か」を
in-memory set で追跡する)。遷移が終わったら (復帰 / 満腹への回復)
呼び出し側が ``clear_down_state`` / ``clear_hunger_max_state`` を呼んで
リセットする。これは ``PlayerDeathGraceTimer`` の register/cancel と同型の
パターン。

``BeliefEvidence.episode_ids`` は必須 (traceability) のため、その being の
**直近の episode** に anchor する。episode が 1 件も無ければ証拠を作らず
skip する (捏造しない。warning ログで可視化)。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Set
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
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

_logger = logging.getLogger(__name__)

_CUE_SIGNATURE_DOWN = "state:down"
_CUE_SIGNATURE_HUNGER_MAX = "state:hunger_max"


class StateCollapseEvidenceTranscriber:
    """is_down への遷移 / hunger max 到達を ``BeliefEvidence`` に転記する。"""

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
        # dedup 状態: 「現在進行中か」を being_id.value の集合で追跡する。
        # down / hunger max は独立の遷移なので別々の集合を持つ。
        self._down_being_ids: Set[str] = set()
        self._hunger_max_being_ids: Set[str] = set()

    def record_down_evidence(self, being_id: BeingId) -> Optional[BeliefEvidence]:
        """is_down への遷移を高 salience evidence として積む (遷移時 1 回のみ)。

        既に down 中 (``clear_down_state`` を呼ばれていない) の being に対して
        再度呼ばれても、二重に積まず None を返す。
        """
        return self._record_if_new(
            being_id,
            tracked_ids=self._down_being_ids,
            cue_signature=_CUE_SIGNATURE_DOWN,
            text="戦闘不能になった。",
        )

    def clear_down_state(self, being_id: BeingId) -> None:
        """復帰時に呼び、down の dedup 状態をリセットする (次回 down で再度積める)。"""
        self._down_being_ids.discard(self._being_key(being_id))

    def record_hunger_max_evidence(
        self, being_id: BeingId
    ) -> Optional[BeliefEvidence]:
        """hunger max 到達を高 salience evidence として積む (到達時 1 回のみ)。

        既に max 張り付き中 (``clear_hunger_max_state`` を呼ばれていない) の
        being に対して再度呼ばれても、二重に積まず None を返す。
        """
        return self._record_if_new(
            being_id,
            tracked_ids=self._hunger_max_being_ids,
            cue_signature=_CUE_SIGNATURE_HUNGER_MAX,
            text="空腹が限界に達した。",
        )

    def clear_hunger_max_state(self, being_id: BeingId) -> None:
        """食事等で hunger が max を下回った時に呼び、dedup 状態をリセットする。"""
        self._hunger_max_being_ids.discard(self._being_key(being_id))

    @staticmethod
    def _being_key(being_id: BeingId) -> str:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return being_id.value

    def _record_if_new(
        self,
        being_id: BeingId,
        *,
        tracked_ids: Set[str],
        cue_signature: str,
        text: str,
    ) -> Optional[BeliefEvidence]:
        key = self._being_key(being_id)
        if key in tracked_ids:
            return None

        recent = self._episode_store.list_recent_by_being(being_id, limit=1)
        if not recent:
            _logger.warning(
                "StateCollapseEvidenceTranscriber: no episode to anchor for "
                "being_id=%s cue_signature=%s; skipping evidence",
                being_id.value,
                cue_signature,
            )
            return None
        anchor_episode = recent[0]

        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.STATE_COLLAPSE,
            episode_ids=(anchor_episode.episode_id,),
            cue_signature=cue_signature,
            text=text,
            salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
            occurred_at=anchor_episode.occurred_at,
            tick=self._resolve_tick(),
        )
        # dedup 状態は evidence を積んだ後に確定させる (episode 未 anchor で
        # skip したときは「進行中」に入れない = 次 tick でも再試行できる)。
        tracked_ids.add(key)
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
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE "
                "(state_collapse); skipping",
                exc_info=True,
            )


__all__ = ["StateCollapseEvidenceTranscriber"]
