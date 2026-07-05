"""U9a/U9b (予測誤差統一設計 部品5・想起の信用割り当て): chunk 主観補完の

完了点で recall buffer 側の該当 observation を扱う共通ロジック。

同期経路 (``EpisodicChunkCoordinator``) と非同期経路 (``InlineEpisodicSubjectiveScheduler`` /
``ThreadPoolEpisodicSubjectiveScheduler``) の 3 箇所から呼ばれるため、U1 の
``_prediction_context_ids_from_encoding`` と同じ「chunk を構成する action 群から
prediction_context_id を重複排除して集める」ロジックをここに集約する。

U9a (外れ側): ``stamp_recall_prediction_outcome_if_applicable`` が
``prediction_error`` 非 None のときに recall observation へ誤差を刻む。
U9b (的中側): ``record_recall_hits_if_applicable`` が ``prediction_error`` が
None (かつ実際に予測を伴う行動があった) のときに、その予測を立てた
in-context episode 群の的中回数を加算する。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    compute_chunk_attribution,
)
from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    IEpisodicRecallSuccessStore,
)
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


def record_recall_hits_if_applicable(
    *,
    recall_buffer_store: Optional[EpisodicRecallBufferRepository],
    recall_success_store: Optional[IEpisodicRecallSuccessStore],
    recall_hit_boost_enabled: bool,
    being_id: Optional[BeingId],
    episode: SubjectiveEpisode,
    chunk_actions: Iterable[Any],
) -> None:
    """U9b: 当たった予測 (episode.prediction_error が None) を、それを立てた

    in-context episode 群の的中回数として的中側 sidecar store に加算する。

    以下のいずれかに該当すれば何もしない (= flag OFF のとき導入前と完全に
    一致する安全な縮退):
    - ``recall_hit_boost_enabled`` が False
    - ``recall_buffer_store`` / ``recall_success_store`` のいずれかが None
      (= 想起の信用割り当て自体が未配線)
    - ``being_id`` が未解決
    - ``episode.prediction_error`` が非 None (= 予測が外れた。U9a の対象)
    - このターンに ``expected_result`` を伴う行動が無かった (= 実際には
      何も予測していない「何もしなかっただけの的中」を水増ししない。U4 の
      CONFIRMATION 転記ガードと同じ ``compute_chunk_attribution`` を再利用)
    - id 機構 OFF で prediction_context_id が 1 つも無い

    record 自体の失敗は turn を止めない (的中側 store は次回以降そのまま
    boost 0 として扱われるだけの安全な縮退)。
    """
    if not recall_hit_boost_enabled:
        return
    if recall_buffer_store is None or recall_success_store is None:
        return
    if being_id is None:
        return
    if episode.prediction_error is not None:
        return
    chunk_actions_tuple = tuple(chunk_actions)
    _in_context_belief_ids, had_expected_result = compute_chunk_attribution(
        chunk_actions_tuple
    )
    if not had_expected_result:
        return
    prediction_context_ids = prediction_context_ids_from_actions(chunk_actions_tuple)
    if not prediction_context_ids:
        return
    for prediction_context_id in prediction_context_ids:
        try:
            episode_ids = recall_buffer_store.list_episode_ids_by_prediction_context_by_being(
                being_id, prediction_context_id
            )
        except Exception:
            _logger.warning(
                "list_episode_ids_by_prediction_context_by_being failed "
                "(episode_id=%s, prediction_context_id=%s); recall hit boost "
                "left unrecorded",
                episode.episode_id,
                prediction_context_id,
                exc_info=True,
            )
            continue
        for hit_episode_id in episode_ids:
            try:
                recall_success_store.record_hit_by_being(being_id, hit_episode_id)
            except Exception:
                _logger.warning(
                    "record_hit_by_being failed (episode_id=%s, "
                    "prediction_context_id=%s); recall hit boost left "
                    "unrecorded",
                    hit_episode_id,
                    prediction_context_id,
                    exc_info=True,
                )


__all__ = [
    "prediction_context_ids_from_actions",
    "stamp_recall_prediction_outcome_if_applicable",
    "record_recall_hits_if_applicable",
]
