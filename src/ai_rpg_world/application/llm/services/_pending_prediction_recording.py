"""U10a (予測誤差統一設計 部品6・pending prediction): chunk 主観補完の

完了点で抽出された約束・見込みを ``PendingPrediction`` 化して per-Being
store に積む共通ロジック。

同期経路 (``EpisodicChunkCoordinator``) と非同期経路
(``InlineEpisodicSubjectiveScheduler`` / ``ThreadPoolEpisodicSubjectiveScheduler``)
の 3 箇所から呼ばれるため、``_recall_prediction_outcome_stamping.py`` と同じ
「完了点の共通ロジックを 1 箇所に集約する」設計に倣う。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from uuid import uuid4

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PendingPredictionRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_logger = logging.getLogger(__name__)


def record_pending_prediction_if_applicable(
    *,
    pending_prediction_store: Optional[PendingPredictionRepository],
    pending_prediction_enabled: bool,
    being_id: Optional[BeingId],
    episode: SubjectiveEpisode,
    current_tick_provider: Optional[Callable[[], Optional[int]]],
    trace_recorder: Optional[ITraceRecorder] = None,
) -> None:
    """抽出された ``episode.pending_prediction_draft`` を ``PendingPrediction``

    化して ``pending_prediction_store`` に積む。

    以下のいずれかに該当すれば何もしない (= flag OFF のとき導入前と完全に
    一致する安全な縮退):
    - ``pending_prediction_enabled`` が False
    - ``pending_prediction_store`` が None (= 未配線)
    - ``episode.pending_prediction_draft`` が None (= この chunk からは
      抽出されなかった)
    - ``being_id`` が未解決
    - ``current_tick_provider`` が None、または呼び出しが例外 / 非 int を返す
      (= LLM は「今から何 tick 後か」という相対オフセットしか知らないため、
      絶対 tick 範囲へ変換できないと安全に skip する)

    書き込み自体の失敗は turn を止めない設計にはしていない (per-Being store
    への append は他の U2/U9a/U9b 系 sidecar と異なり「新しい約束を 1 件
    足すだけ」の単純操作で、失敗時は VO 自体のバリデーション例外である
    可能性が高く、握りつぶすと乱発抽出のバグが見えなくなるため呼び出し元に
    伝播させる)。
    """
    if not pending_prediction_enabled or pending_prediction_store is None:
        return
    draft = episode.pending_prediction_draft
    if draft is None:
        return
    if being_id is None:
        return
    if current_tick_provider is None:
        return
    try:
        created_tick = current_tick_provider()
    except Exception:
        _logger.warning(
            "current_tick_provider raised while recording pending prediction; "
            "skipping (episode_id=%s)",
            episode.episode_id,
            exc_info=True,
        )
        return
    if not isinstance(created_tick, int) or isinstance(created_tick, bool):
        return

    pending = PendingPrediction(
        pending_id=f"pending-{uuid4().hex}",
        text=draft.text,
        resolution_cues=draft.resolution_cues,
        tick_from=created_tick + draft.tick_offset_from,
        tick_to=created_tick + draft.tick_offset_to,
        origin_episode_id=episode.episode_id,
        created_tick=created_tick,
        kind=draft.kind,  # P11: 種別 (promise / plan) を draft から引き継ぐ
    )
    pending_prediction_store.add_by_being(being_id, pending)

    if trace_recorder is not None:
        try:
            trace_recorder.record(
                TraceEventKind.PENDING_PREDICTION_CREATED,
                tick=created_tick,
                pending_id=pending.pending_id,
                being_id=str(being_id.value),
                origin_episode_id=pending.origin_episode_id,
                resolution_cues=list(pending.resolution_cues),
                tick_from=pending.tick_from,
                tick_to=pending.tick_to,
                # P11: 種別 (promise / plan) の区別。payload キーは pending_kind に
                # する (record の第 1 引数 kind = event 種別と衝突するため)。
                pending_kind=pending.kind,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for PENDING_PREDICTION_CREATED; "
                "skipping",
                exc_info=True,
            )


__all__ = ["record_pending_prediction_if_applicable"]
