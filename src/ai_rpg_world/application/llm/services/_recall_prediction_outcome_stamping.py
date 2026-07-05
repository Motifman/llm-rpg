"""U9a (予測誤差統一設計 部品5・誤差駆動再解釈): chunk 主観補完の完了点で

recall buffer 側の該当 observation に prediction_error を刻む共通ロジック。

同期経路 (``EpisodicChunkCoordinator``) と非同期経路 (``InlineEpisodicSubjectiveScheduler`` /
``ThreadPoolEpisodicSubjectiveScheduler``) の 3 箇所から呼ばれるため、U1 の
``_prediction_context_ids_from_encoding`` と同じ「chunk を構成する action 群から
prediction_context_id を重複排除して集める」ロジックをここに集約する。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_logger = logging.getLogger(__name__)


def prediction_context_ids_from_actions(actions: Iterable[Any]) -> list[str]:
    """chunk を構成する action 群から prediction_context_id を重複排除して集める。

    U1 (``episodic_subjective_completion_schedulers.py::_prediction_context_ids_from_encoding``)
    と同じロジック。id 機構が OFF (= 発行された id が 1 つも無い) のときは
    空リストを返す。
    """
    ids: list[str] = []
    try:
        for action in actions:
            pid = getattr(action, "prediction_context_id", None)
            if pid and pid not in ids:
                ids.append(pid)
    except Exception:
        return []
    return ids


def stamp_recall_prediction_outcome_if_applicable(
    *,
    recall_buffer_store: Optional[EpisodicRecallBufferRepository],
    error_driven_reinterpretation_enabled: bool,
    being_id: Optional[BeingId],
    episode: SubjectiveEpisode,
    chunk_actions: Iterable[Any],
) -> None:
    """U9a: 外れた予測 (episode.prediction_error が非 None) を、それを立てた

    in-context recall observation 群に刻む。

    以下のいずれかに該当すれば何もしない (= flag OFF のとき導入前と完全に
    一致する安全な縮退):
    - ``error_driven_reinterpretation_enabled`` が False
    - ``recall_buffer_store`` が None (= reinterpretation 自体が未配線)
    - ``being_id`` が未解決
    - ``episode.prediction_error`` が None (= 予測が外れていない、または
      予測自体が無かった)
    - id 機構 OFF で prediction_context_id が 1 つも無い

    stamp 自体の失敗は turn を止めない (recall buffer は次回の再解釈で
    誤差なしのまま扱われるだけの安全な縮退)。
    """
    if not error_driven_reinterpretation_enabled:
        return
    if recall_buffer_store is None or being_id is None:
        return
    prediction_error = episode.prediction_error
    if prediction_error is None:
        return
    prediction_context_ids = prediction_context_ids_from_actions(chunk_actions)
    if not prediction_context_ids:
        return
    for prediction_context_id in prediction_context_ids:
        try:
            recall_buffer_store.stamp_prediction_outcome_by_being(
                being_id, prediction_context_id, prediction_error
            )
        except Exception:
            _logger.warning(
                "stamp_prediction_outcome_by_being failed (episode_id=%s, "
                "prediction_context_id=%s); recall buffer left unstamped",
                episode.episode_id,
                prediction_context_id,
                exc_info=True,
            )


__all__ = [
    "prediction_context_ids_from_actions",
    "stamp_recall_prediction_outcome_if_applicable",
]
