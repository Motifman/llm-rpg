"""Episode store から受動想起用候補を、時間軸と cue 軸の和集合で取る純粋ロジック（prompt / LLM 未接続）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import IEpisodicEpisodeStore
from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue, SubjectiveEpisode

PASSIVE_RECALL_AXIS_TEMPORAL = "temporal"


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


def passive_recall_cue_axis_source_label(cue: EpisodicCue) -> str:
    """situation cue の軸種別ごとのデバッグ・平等枠ラベル（例: cue:place_spot, cue:entity）。"""
    return f"cue:{cue.axis}"


def passive_recall_cue_axis_label(cue: EpisodicCue) -> str:
    """後方互換・テスト用エイリアス。`cue:{cue.axis}` と同じ。"""
    return passive_recall_cue_axis_source_label(cue)


@dataclass(frozen=True)
class EpisodicPassiveRecallCandidate:
    episode: SubjectiveEpisode
    """和集合後、この episode がヒットした検索軸（辞書順で安定）。"""
    source_axes: tuple[str, ...]


@dataclass(frozen=True)
class EpisodicPassiveRecallRetrievalDebug:
    """各軸の候補リスト長（fetch 後・各軸 limit 適用後）。"""
    raw_row_count_by_axis: tuple[tuple[str, int], ...]
    """全軸の候補を episode_id で重複排除したユニーク件数（round-robin / max_candidates 前）。"""
    union_episode_count_before_max_cap: int
    """最終候補ごとの episode_id と source_axes（ヒットした全軸）。"""
    candidate_episode_sources: tuple[tuple[str, tuple[str, ...]], ...]
    """最終リストにおいて、各軸ラベルを source に持つ episode 数。"""
    final_episode_count_by_source_axis: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EpisodicPassiveRecallRetrievalResult:
    candidates: tuple[EpisodicPassiveRecallCandidate, ...]
    debug: EpisodicPassiveRecallRetrievalDebug


class EpisodicPassiveRecallRetrievalService:
    """
    時間軸（list_recent）と cue 軸（list_by_cue、cue.axis 単位でまとめる）から候補を取る。
    各軸は最大 limit_per_axis 件（軸内は occurred_at / episode_id 降順）。
    最終採用は全体時刻順ではなく temporal と各 cue:{axis} を同格で round-robin。
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
        temporal_rows = self._store.list_recent(player_id, limit_per_axis)

        axis_order: list[str] = []
        axis_to_cues: dict[str, list[EpisodicCue]] = defaultdict(list)
        seen_canonical_per_axis: dict[str, set[str]] = defaultdict(set)
        for cue in situation_cues:
            ax = cue.axis
            ck = cue.to_canonical()
            if ck in seen_canonical_per_axis[ax]:
                continue
            seen_canonical_per_axis[ax].add(ck)
            axis_to_cues[ax].append(cue)
            if len(axis_to_cues[ax]) == 1:
                axis_order.append(ax)

        cue_arms: list[tuple[str, list[SubjectiveEpisode]]] = []
        for ax in axis_order:
            merged: dict[str, SubjectiveEpisode] = {}
            for cue in axis_to_cues[ax]:
                for ep in self._store.list_by_cue(player_id, cue, limit_per_axis):
                    merged[ep.episode_id] = ep
            ordered = sorted(merged.values(), key=_occurrence_sort_key, reverse=True)
            if limit_per_axis > 0:
                ordered = ordered[:limit_per_axis]
            cue_arms.append((f"cue:{ax}", ordered))

        raw_counts: list[tuple[str, int]] = [(PASSIVE_RECALL_AXIS_TEMPORAL, len(temporal_rows))]
        raw_counts.extend((lab, len(rows)) for lab, rows in cue_arms)

        episode_by_id: dict[str, SubjectiveEpisode] = {}
        source_axes_by_episode: dict[str, set[str]] = defaultdict(set)

        for ep in temporal_rows:
            episode_by_id[ep.episode_id] = ep
            source_axes_by_episode[ep.episode_id].add(PASSIVE_RECALL_AXIS_TEMPORAL)

        for label, rows in cue_arms:
            for ep in rows:
                episode_by_id[ep.episode_id] = ep
                source_axes_by_episode[ep.episode_id].add(label)

        union_before_cap = len(episode_by_id)

        arms: list[tuple[str, list[SubjectiveEpisode]]] = [
            (PASSIVE_RECALL_AXIS_TEMPORAL, temporal_rows),
            *cue_arms,
        ]

        capped_ids = _round_robin_pick_episode_ids(arms, max_candidates)

        candidates: list[EpisodicPassiveRecallCandidate] = []
        candidate_sources: list[tuple[str, tuple[str, ...]]] = []
        axis_hits: defaultdict[str, int] = defaultdict(int)

        for eid in capped_ids:
            ep = episode_by_id[eid]
            axes = tuple(sorted(source_axes_by_episode[eid]))
            candidates.append(EpisodicPassiveRecallCandidate(episode=ep, source_axes=axes))
            candidate_sources.append((eid, axes))
            for ax in source_axes_by_episode[eid]:
                axis_hits[ax] += 1

        final_axis_counts = tuple(sorted(axis_hits.items(), key=lambda t: t[0]))

        debug = EpisodicPassiveRecallRetrievalDebug(
            raw_row_count_by_axis=tuple(raw_counts),
            union_episode_count_before_max_cap=union_before_cap,
            candidate_episode_sources=tuple(candidate_sources),
            final_episode_count_by_source_axis=final_axis_counts,
        )
        return EpisodicPassiveRecallRetrievalResult(candidates=tuple(candidates), debug=debug)


def _round_robin_pick_episode_ids(
    arms: list[tuple[str, list[SubjectiveEpisode]]],
    max_candidates: int,
) -> list[str]:
    """
    各軸リストを occurred_at 順に保ちつつ、軸を巡回して episode_id を採用する。
    同一 episode は出力に 1 度だけ含め、重複はスキップして当該軸のポインタのみ進める。
    """

    if max_candidates <= 0 or not arms:
        return []

    ptr = [0] * len(arms)
    out: list[str] = []
    chosen: set[str] = set()

    while len(out) < max_candidates:
        progressed = False
        for i, (_label, lst) in enumerate(arms):
            if len(out) >= max_candidates:
                break
            while ptr[i] < len(lst):
                eid = lst[ptr[i]].episode_id
                ptr[i] += 1
                if eid not in chosen:
                    chosen.add(eid)
                    out.append(eid)
                    progressed = True
                    break
        if not progressed:
            break

    return out
