"""U10b (予測誤差統一設計 部品6・pending prediction 清算): chunk 主観補完の

完了点で、再浮上していた約束の「果たされた / 破られた」判定を
``PENDING_RESOLUTION`` evidence に転記し、決着した約束と期限切れの約束を
per-Being store から除く共通ロジック。

``record_pending_prediction_if_applicable`` (抽出・保持) と対をなす。同期経路
(``EpisodicChunkCoordinator``) と非同期経路 (スケジューラ 2 種) の 3 箇所から
呼ばれるため、``_recall_prediction_outcome_stamping.py`` /
``_pending_prediction_recording.py`` と同じ「完了点の共通ロジックを 1 箇所に
集約する」設計に倣う。

## 3 つの後始末を 1 回の replace で行う

1. **清算**: LLM が下した ``pending_resolution_verdicts`` のうち、いま store に
   実在する約束にマッチするものを evidence に転記し、store から除く
   (fulfilled → 対象人物への支持 / broken → 反証。判定は chunk 補完 LLM が
   済ませており、本モジュールは転記のみ)。
2. **失効**: ``tick_to`` を過ぎても決着しなかった約束を黙って除く
   (= 人間でも忘れられた約束は消える。統一設計の「判定つかず期限切れは
   静かに失効」)。
3. store の書き換えは清算分と失効分をまとめた 1 回の ``replace_all_by_being``
   で行う (read-modify-write を 1 度に済ませ、``PendingPredictionRepository``
   に削除専用 primitive を足さずに済ませる設計判断)。

flag OFF / store 未配線 / being 未解決のときは何もしない (= 導入前と完全に
一致する安全な縮退)。evidence transcriber が未配線 (``BELIEF_EVIDENCE_ENABLED``
が OFF) のときは、evidence は積まないが清算・失効による store の後始末は
行う (約束が store に溜まり続けるのを防ぐ。学習経路自体が OFF なので失われる
学びは無い)。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PendingPredictionRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
        BeliefEvidenceTranscriber,
    )

_logger = logging.getLogger(__name__)


def resolve_pending_predictions_if_applicable(
    *,
    pending_prediction_store: Optional[PendingPredictionRepository],
    pending_prediction_enabled: bool,
    being_id: Optional[BeingId],
    episode: SubjectiveEpisode,
    belief_evidence_transcriber: Optional["BeliefEvidenceTranscriber"],
    current_tick_provider: Optional[Callable[[], Optional[int]]],
    trace_recorder: Optional[ITraceRecorder] = None,
) -> None:
    """``episode.pending_resolution_verdicts`` を清算し、期限切れの約束を失効させる。

    以下のいずれかに該当すれば何もしない (flag OFF 時に導入前と完全一致):
    - ``pending_prediction_enabled`` が False
    - ``pending_prediction_store`` が None (= 未配線)
    - ``being_id`` が未解決
    """
    if not pending_prediction_enabled or pending_prediction_store is None:
        return
    if being_id is None:
        return

    # 単一 writer 前提: ここからの「list_all_by_being → replace_all_by_being」
    # は複合の read-modify-write で、store のメソッド単位ロック (RLock) では
    # list と replace の間の窓は守れない (窓の間に別 thread が add した約束は
    # replace で消える)。現状この清算と record (add) は
    # ThreadPoolEpisodicSubjectiveScheduler の既定 max_workers=1 により同一
    # worker thread で直列に走るため安全。scheduler を複数 worker 化するとき
    # は、清算と記録を being 単位で直列化する仕組みが別途必要になる。
    try:
        live = pending_prediction_store.list_all_by_being(being_id)
    except Exception:
        _logger.warning(
            "pending_prediction_store.list_all_by_being failed; skipping resolution",
            exc_info=True,
        )
        return
    if not live:
        return

    by_id = {p.pending_id: p for p in live}
    resolved_ids: set[str] = set()

    # 1. 清算: LLM が決着させた約束を evidence に転記して除く。
    for verdict in episode.pending_resolution_verdicts:
        pending = by_id.get(verdict.pending_id)
        if pending is None:
            # prompt に載せた約束が既に別経路で消えている等。安全に無視。
            continue
        evidence_id: Optional[str] = None
        if belief_evidence_transcriber is not None:
            try:
                evidence = belief_evidence_transcriber.record_pending_resolution(
                    being_id, episode, pending, verdict=verdict.verdict
                )
                evidence_id = evidence.evidence_id if evidence is not None else None
            except Exception:
                _logger.warning(
                    "record_pending_resolution failed (pending_id=%s); "
                    "still removing the pending",
                    pending.pending_id,
                    exc_info=True,
                )
        resolved_ids.add(pending.pending_id)
        _emit_resolved_trace(
            trace_recorder,
            being_id=being_id,
            pending=pending,
            verdict=verdict.verdict,
            evidence_id=evidence_id,
        )

    # 2. 失効: tick_to を過ぎても決着しなかった約束を黙って除く。
    current_tick = _resolve_tick(current_tick_provider)
    expired_ids: set[str] = set()
    if current_tick is not None:
        expired_ids = {
            p.pending_id
            for p in live
            if p.pending_id not in resolved_ids and current_tick > p.tick_to
        }

    # 3. 清算分 + 失効分をまとめて 1 回の replace で除く。
    drop = resolved_ids | expired_ids
    if not drop:
        return
    survivors = [p for p in live if p.pending_id not in drop]
    try:
        pending_prediction_store.replace_all_by_being(being_id, survivors)
    except Exception:
        _logger.warning(
            "pending_prediction_store.replace_all_by_being failed; "
            "pending store may retain resolved/expired entries",
            exc_info=True,
        )
        return
    if expired_ids:
        _emit_expired_trace(
            trace_recorder,
            being_id=being_id,
            expired_ids=expired_ids,
            # P11: 失効した約束の種別 (promise / plan)。CREATED / RESOLVED と
            # 揃え、M-run 分析で「方針予測が期限切れで失効した」を「約束が
            # 失効した」と区別できるようにする。
            expired_kinds={
                p.pending_id: p.kind for p in live if p.pending_id in expired_ids
            },
            tick=current_tick,
        )


def _resolve_tick(
    current_tick_provider: Optional[Callable[[], Optional[int]]],
) -> Optional[int]:
    if current_tick_provider is None:
        return None
    try:
        tick = current_tick_provider()
    except Exception:
        _logger.debug("current_tick_provider raised; tick left as None", exc_info=True)
        return None
    if not isinstance(tick, int) or isinstance(tick, bool):
        return None
    return tick


def _emit_resolved_trace(
    trace_recorder: Optional[ITraceRecorder],
    *,
    being_id: BeingId,
    pending,
    verdict: str,
    evidence_id: Optional[str],
) -> None:
    if trace_recorder is None:
        return
    try:
        trace_recorder.record(
            TraceEventKind.PENDING_PREDICTION_RESOLVED,
            tick=pending.tick_to,
            pending_id=pending.pending_id,
            being_id=str(being_id.value),
            verdict=verdict,
            evidence_id=evidence_id,
            origin_episode_id=pending.origin_episode_id,
            # P11: 種別 (promise / plan) の区別。payload キーは pending_kind に
            # する (record の第 1 引数 kind = event 種別と衝突するため)。
            pending_kind=pending.kind,
        )
    except Exception:
        _logger.debug(
            "trace recorder.record raised for PENDING_PREDICTION_RESOLVED; skipping",
            exc_info=True,
        )


def _emit_expired_trace(
    trace_recorder: Optional[ITraceRecorder],
    *,
    being_id: BeingId,
    expired_ids: set[str],
    expired_kinds: dict[str, str],
    tick: Optional[int],
) -> None:
    if trace_recorder is None:
        return
    try:
        trace_recorder.record(
            TraceEventKind.PENDING_PREDICTION_EXPIRED,
            tick=tick,
            being_id=str(being_id.value),
            pending_ids=sorted(expired_ids),
            # P11: id → 種別 (promise / plan)。payload キーは event 種別引数
            # kind との衝突を避けるため pending_kinds にする。
            pending_kinds={pid: expired_kinds[pid] for pid in sorted(expired_ids)},
        )
    except Exception:
        _logger.debug(
            "trace recorder.record raised for PENDING_PREDICTION_EXPIRED; skipping",
            exc_info=True,
        )


__all__ = ["resolve_pending_predictions_if_applicable"]
