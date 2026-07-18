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

## PR-C: 共在ゲート (fulfilled 判定の妥当性検証)

m7_v3coop_001 の t188 で、リオが「下山してカイたちと合流する」と*思っただけ*
なのに chunk 主観補完 LLM が合流の約束を fulfilled と誤判定し、現実に反する
「果たした」evidence が belief を汚染する事故が観測された。fulfilled は相手
への信頼を強化する evidence になるため、この種の誤判定は素通しできない。

ゲート対象は **fulfilled 判定かつ resolution_cues に ``player:X`` を含む**
場合のみ (broken 判定・player cue の無い約束は一切変更しない)。約束の相手
全員 (複数 player cue のときは全員必須) がその chunk に共在していたことを
fulfilled 受理の必要条件にする。

照合材料をエンジン由来の確定事実に限定するのは、エージェント自身の
inner_thought / memo / 観測 prose テキストを使うと「カイたちと合流しよう」
という自己記述に相手の名前が書いてあるだけで素通しし、ゲートの意味が無く
なるため。

## PR-M: 照合材料を who ∪ co_present に広げる

PR-C は照合材料を ``episode.who`` に限定していたが、``who`` は「その chunk で
実際に structured.actor として動作した人」しか集めない (無状態な収集)。その
結果、同じスポットに居ても黙っている相手は ``who`` に入らず、相手が実在する
のに fulfilled が誤棄却され、約束がそのまま期限切れで消える事故が起きた
(r1_003 で 12 件の fulfilled が誤棄却され、位置データで再構成すると 12 件中
11 件は要求相手が同一スポットに実在していた)。

そこで ``episode.co_present`` (= chunk を閉じた時点で同じスポットに居た他
プレイヤー名。エンジン由来の確定事実) を新設し、照合を ``who ∪ co_present``
に対して行う。「ルールを増やさず照合材料を正しくする」修正で、ゲートの意味
(自己記述だけでは素通ししない) は保ったまま「相手が黙っていても同席して
いれば清算を通す」ようにする。co_present の供給源は chunk write 時の
``ToolRuntimeContextDto`` の同席プレイヤー (= prompt の「同じ場所にいる
プレイヤー」節と同じ occupancy) で、``ChunkEpisodeDraftBuilder`` が episode に
刻印する。

条件を満たさない fulfilled は **棄却して約束を保留のまま store に残す**
(drain しない)。期限が来れば従来どおり黙って失効する。fulfilled を broken に
書き換えるような判定の捏造は絶対に行わない (= 誤棄却されても既存の安全な
「保留 → 失効」に縮退するだけで、虚偽の反証を刻まない)。棄却は
``TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED`` で trace に残す。

**既知の限界**: 「X のために単独でやる」型の約束 (相手が resolution_cues の
player cue に含まれているが、成立に相手の同席を要さないもの) は、このゲートに
よって誤棄却されうる。ただし誤棄却の結果は「保留のまま残り、期限が来れば
失効する」という既存の安全な縮退先に落ちるため、虚偽の fulfilled evidence が
刻まれるより安全側に倒れる。棄却率は ``PENDING_PREDICTION_VERDICT_REJECTED``
trace で実測できる。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PendingPredictionRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PENDING_VERDICT_FULFILLED,
    PendingPrediction,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

# PR-C (共在ゲート): resolution_cues のうち人物指定 cue の prefix。
_PLAYER_CUE_PREFIX = "player:"

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

    # LOW-2: RESOLVED trace の tick には実際に清算された現在 tick を使う
    # (窓の終端 tick_to を使うと、窓の早い時点で果たされた約束が trace 上は
    # 未来の tick に記録され、CREATED / EXPIRED (どちらも現在 tick) と非対称に
    # なる)。失効判定 (step 2) でも同じ current_tick を使う。
    current_tick = _resolve_tick(current_tick_provider)

    # 1. 清算: LLM が決着させた約束を evidence に転記して除く。
    for verdict in episode.pending_resolution_verdicts:
        pending = by_id.get(verdict.pending_id)
        if pending is None:
            # prompt に載せた約束が既に別経路で消えている等。安全に無視。
            continue

        # PR-C (共在ゲート): fulfilled かつ player cue を含む約束は、相手が
        # 判定 chunk に共在していたこと (エンジン由来の確定事実) を必要条件に
        # する。broken 判定・player cue の無い約束は対象外。
        #
        # PR-M: 照合材料を episode.who だけでなく co_present との和集合にする。
        # who は「実際に動作した人」しか集めないため、同席していても黙っている
        # 相手は who に入らず fulfilled を誤棄却していた (r1_003 で 12 件)。
        # co_present (= その場に居た人) を足すことで「相手が黙っていても同席
        # していれば清算を通す」。順序は who を先に、続けて co_present の順で
        # 重複除去する (trace の present_players / missing_players の再現性のため)。
        if verdict.verdict == PENDING_VERDICT_FULFILLED:
            required = _required_players(pending)
            if required:
                present = tuple(dict.fromkeys((*episode.who, *episode.co_present)))
                missing = _missing_players(required, present)
                if missing:
                    _emit_rejected_trace(
                        trace_recorder,
                        being_id=being_id,
                        pending=pending,
                        verdict=verdict.verdict,
                        required_players=required,
                        missing_players=missing,
                    )
                    # 保留のまま残す (drain しない)。fulfilled を broken に
                    # 書き換える等の判定の捏造は行わない。
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
            tick=current_tick,
        )

    # 2. 失効: tick_to を過ぎても決着しなかった約束を黙って除く。
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


def _required_players(pending: "PendingPrediction") -> tuple[str, ...]:
    """``resolution_cues`` のうち ``player:X`` の X (相手の名前) 全員を返す。

    順序は ``resolution_cues`` の記載順を保つ (trace の再現性のため)。
    """
    return tuple(
        cue[len(_PLAYER_CUE_PREFIX):]
        for cue in pending.resolution_cues
        if cue.startswith(_PLAYER_CUE_PREFIX)
    )


def _missing_players(
    required: tuple[str, ...], present: tuple[str, ...]
) -> tuple[str, ...]:
    """``required`` (約束の相手全員) のうち ``present`` に不在の名前を返す。

    ``present`` は共在の照合材料 (who ∪ co_present)。「約束の相手全員」の共在
    を要求する仕様 (複数 player cue のときも全員必須) のため、1 人でも不在なら
    non-empty を返す。
    """
    return tuple(name for name in required if name not in present)


def _emit_rejected_trace(
    trace_recorder: Optional[ITraceRecorder],
    *,
    being_id: BeingId,
    pending: "PendingPrediction",
    verdict: str,
    required_players: tuple[str, ...],
    missing_players: tuple[str, ...],
) -> None:
    if trace_recorder is None:
        return
    present_players = tuple(name for name in required_players if name not in missing_players)
    try:
        trace_recorder.record(
            TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED,
            being_id=str(being_id.value),
            pending_id=pending.pending_id,
            verdict=verdict,
            required_players=list(required_players),
            present_players=list(present_players),
            missing_players=list(missing_players),
        )
    except Exception:
        _logger.debug(
            "trace recorder.record raised for PENDING_PREDICTION_VERDICT_REJECTED; "
            "skipping",
            exc_info=True,
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
    tick: Optional[int],
) -> None:
    if trace_recorder is None:
        return
    try:
        trace_recorder.record(
            TraceEventKind.PENDING_PREDICTION_RESOLVED,
            # LOW-2: tick は実際に清算された現在 tick (窓の終端 tick_to では
            # ない)。窓の情報は tick_from / tick_to として payload に残す。
            tick=tick,
            pending_id=pending.pending_id,
            being_id=str(being_id.value),
            verdict=verdict,
            evidence_id=evidence_id,
            origin_episode_id=pending.origin_episode_id,
            tick_from=pending.tick_from,
            tick_to=pending.tick_to,
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
