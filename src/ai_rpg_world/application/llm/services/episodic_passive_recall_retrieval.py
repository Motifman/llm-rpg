"""Episode store から受動想起用候補を、時間軸と cue 軸の和集合で取る純粋ロジック（prompt / LLM 未接続）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import IEpisodicEpisodeStore
from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue, SubjectiveEpisode

PASSIVE_RECALL_AXIS_RECENT = "recent"


def _occurrence_sort_key(ep: SubjectiveEpisode) -> tuple[datetime, str]:
    """
    IEpisodicEpisodeStore の並び（occurred_at 降順、同一時刻は episode_id 降順）と整合するキー。
    naive datetime は UTC 相当として比較する（本体は変更しない）。
    """

    dt = ep.occurred_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return (dt, ep.episode_id)


def passive_recall_cue_axis_label(cue: EpisodicCue) -> str:
    """cue 軸のデバッグ用ラベル（canonical と 1:1）。"""
    return f"cue:{cue.to_canonical()}"


@dataclass(frozen=True)
class EpisodicPassiveRecallCandidate:
    episode: SubjectiveEpisode
    """和集合マージ後、この episode に寄与した検索軸（辞書順で安定）。"""
    source_axes: tuple[str, ...]


@dataclass(frozen=True)
class EpisodicPassiveRecallRetrievalDebug:
    """各軸の list_* が返した行数（重複は軸内では store 次第だが、軸ごとの件数）。"""
    raw_row_count_by_axis: tuple[tuple[str, int], ...]
    """episode_id で重複排除した後のユニーク件数（max_candidates 前）。"""
    union_episode_count_before_max_cap: int
    """最終候補ごとの episode_id と source_axes。"""
    candidate_episode_sources: tuple[tuple[str, tuple[str, ...]], ...]
    """最終リストにおいて、各軸ラベルを source に持つ episode 数（時間軸一辺倒かどうかの目視用）。"""
    final_episode_count_by_source_axis: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EpisodicPassiveRecallRetrievalResult:
    candidates: tuple[EpisodicPassiveRecallCandidate, ...]
    debug: EpisodicPassiveRecallRetrievalDebug


class EpisodicPassiveRecallRetrievalService:
    """
    時間軸（list_recent）と cue 軸（list_by_cue）の候補を取り、episode_id で和集合する。
    並びは occurred_at / episode_id の単純降順（ストア契約と一致）。軸寄与は debug で確認する。
    """

    def __init__(self, store: IEpisodicEpisodeStore) -> None:
        self._store = store

    def retrieve(
        self,
        *,
        player_id: int,
        situation_cues: Sequence[EpisodicCue],
        limit_per_axis: int,
        max_candidates: int,
    ) -> EpisodicPassiveRecallRetrievalResult:
        recent_rows = self._store.list_recent(player_id, limit_per_axis)

        seen_canonical: dict[str, None] = {}
        unique_cues_ordered: list[EpisodicCue] = []
        for cue in situation_cues:
            ck = cue.to_canonical()
            if ck not in seen_canonical:
                seen_canonical[ck] = None
                unique_cues_ordered.append(cue)

        cue_axis_rows: list[tuple[str, list[SubjectiveEpisode]]] = []
        for cue in unique_cues_ordered:
            label = passive_recall_cue_axis_label(cue)
            cue_axis_rows.append((label, self._store.list_by_cue(player_id, cue, limit_per_axis)))

        raw_counts: list[tuple[str, int]] = [(PASSIVE_RECALL_AXIS_RECENT, len(recent_rows))]
        raw_counts.extend((label, len(rows)) for label, rows in cue_axis_rows)

        episode_by_id: dict[str, SubjectiveEpisode] = {}
        source_axes_by_episode: dict[str, set[str]] = defaultdict(set)

        for ep in recent_rows:
            episode_by_id[ep.episode_id] = ep
            source_axes_by_episode[ep.episode_id].add(PASSIVE_RECALL_AXIS_RECENT)

        for axis_label, rows in cue_axis_rows:
            for ep in rows:
                episode_by_id[ep.episode_id] = ep
                source_axes_by_episode[ep.episode_id].add(axis_label)

        union_before_cap = len(episode_by_id)
        merged = sorted(episode_by_id.values(), key=_occurrence_sort_key, reverse=True)
        if max_candidates <= 0:
            capped = []
        else:
            capped = merged[:max_candidates]

        candidates: list[EpisodicPassiveRecallCandidate] = []
        candidate_sources: list[tuple[str, tuple[str, ...]]] = []
        axis_hits: defaultdict[str, int] = defaultdict(int)

        for ep in capped:
            axes = tuple(sorted(source_axes_by_episode[ep.episode_id]))
            candidates.append(EpisodicPassiveRecallCandidate(episode=ep, source_axes=axes))
            candidate_sources.append((ep.episode_id, axes))
            for ax in source_axes_by_episode[ep.episode_id]:
                axis_hits[ax] += 1

        final_axis_counts = tuple(sorted(axis_hits.items(), key=lambda t: t[0]))

        debug = EpisodicPassiveRecallRetrievalDebug(
            raw_row_count_by_axis=tuple(raw_counts),
            union_episode_count_before_max_cap=union_before_cap,
            candidate_episode_sources=tuple(candidate_sources),
            final_episode_count_by_source_axis=final_axis_counts,
        )
        return EpisodicPassiveRecallRetrievalResult(candidates=tuple(candidates), debug=debug)
