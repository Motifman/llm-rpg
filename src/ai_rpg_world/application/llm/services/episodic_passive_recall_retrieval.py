"""Episode store から受動想起用候補を、時間軸と cue 軸の和集合で取る純粋ロジック（prompt / LLM 未接続）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import IEpisodicEpisodeStore
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import IMemoryLinkStore
from ai_rpg_world.application.llm.services.episodic_spreading_activation import (
    neighbor_priming_scores,
)
from ai_rpg_world.application.llm.passive_recall_cue_families import (
    PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY,
    PASSIVE_RECALL_PLACE_FAMILY_LABEL,
    passive_recall_cue_bucket_key,
    passive_recall_object_value_granularity_weight,
    passive_recall_place_axis_granularity_weight,
)

PASSIVE_RECALL_AXIS_TEMPORAL = "temporal"
PASSIVE_RECALL_AXIS_SPREADING = "spreading"


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


def _episode_arm_sort_quality(
    bucket: str,
    cue_axis: str,
) -> bool:
    return bucket == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY or cue_axis == "object"


def _merged_ordered_episodes_for_cue_bucket(
    store: IEpisodicEpisodeStore,
    player_id: int,
    *,
    bucket: str,
    cues: Sequence[EpisodicCue],
    limit_per_axis: int,
) -> tuple[str, list[SubjectiveEpisode], dict[str, frozenset[str]]]:
    """
    単一論理バケツ内で list_by_cue を統合する。
    place ファミリーはラウンドロビン・ラベルが cue:place_family、ソースは cue:{axis} のまま。
    object および place は粒度の高い一致を arm 内の並びで優先する。
    """

    rr_label = (
        PASSIVE_RECALL_PLACE_FAMILY_LABEL
        if bucket == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY
        else f"cue:{cues[0].axis}"
    )
    cue_axis = cues[0].axis
    use_quality = _episode_arm_sort_quality(bucket, cue_axis)

    merged: dict[str, SubjectiveEpisode] = {}
    labels_by_ep: dict[str, set[str]] = defaultdict(set)
    max_gran: dict[str, float] = defaultdict(float)

    for cue in cues:
        ax_label = passive_recall_cue_axis_source_label(cue)
        if bucket == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY:
            g_weight = passive_recall_place_axis_granularity_weight(cue.axis)
        elif cue.axis == "object":
            g_weight = passive_recall_object_value_granularity_weight(cue.value)
        else:
            g_weight = 0.0

        for ep in store.list_by_cue(player_id, cue, limit_per_axis):
            eid = ep.episode_id
            merged[eid] = ep
            labels_by_ep[eid].add(ax_label)
            if use_quality:
                max_gran[eid] = max(max_gran[eid], g_weight)

    def arm_sort_key(ep: SubjectiveEpisode) -> tuple[float, datetime, str]:
        gran = max_gran[ep.episode_id] if use_quality else 0.0
        dt, eid = _occurrence_sort_key(ep)
        return (gran, dt, eid)

    ordered = sorted(merged.values(), key=arm_sort_key, reverse=True)
    if limit_per_axis > 0:
        ordered = ordered[:limit_per_axis]

    labels_frozen = {eid: frozenset(ls) for eid, ls in labels_by_ep.items()}
    return rr_label, ordered, labels_frozen


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
    時間軸（list_recent）と cue 軸（list_by_cue）から候補を取る。
    situation の場所関連軸は論理ファミリー（place_spot / sub_loc / tile_area）として 1 本の軸ブロックにまとめる。
    ブロック内は場所粒度・object は value のプレフィックス粒度で並べ替える（細かい一致を先に）。
    各論理軸ブロックは最大 limit_per_axis 件（適用後）。
    temporal と cue ブロック群はこれまでどおり同等に round-robin。
    """

    def __init__(
        self,
        store: IEpisodicEpisodeStore,
        *,
        link_store: IMemoryLinkStore | None = None,
        spreading_max_hops: int = 2,
    ) -> None:
        self._store = store
        self._link_store = link_store
        self._spreading_max_hops = spreading_max_hops

    def retrieve(
        self,
        *,
        player_id: int,
        situation_cues: Sequence[EpisodicCue],
        limit_per_axis: int,
        max_candidates: int,
        now: datetime | None = None,
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
            bucket = passive_recall_cue_bucket_key(ax)
            axis_to_cues[bucket].append(cue)
            if len(axis_to_cues[bucket]) == 1:
                axis_order.append(bucket)

        cue_arms: list[tuple[str, list[SubjectiveEpisode], dict[str, frozenset[str]]]] = []
        for bucket in axis_order:
            cues = axis_to_cues[bucket]
            rr_label, rows, granular = _merged_ordered_episodes_for_cue_bucket(
                self._store,
                player_id,
                bucket=bucket,
                cues=cues,
                limit_per_axis=limit_per_axis,
            )
            cue_arms.append((rr_label, rows, granular))

        episode_by_id: dict[str, SubjectiveEpisode] = {}
        source_axes_by_episode: dict[str, set[str]] = defaultdict(set)

        for ep in temporal_rows:
            episode_by_id[ep.episode_id] = ep
            source_axes_by_episode[ep.episode_id].add(PASSIVE_RECALL_AXIS_TEMPORAL)

        for _, rows, granular in cue_arms:
            for ep in rows:
                eid = ep.episode_id
                episode_by_id[eid] = ep
                for ax in granular.get(eid, ()):
                    source_axes_by_episode[eid].add(ax)

        effective_now = now if now is not None else datetime.now(timezone.utc)
        spreading_rows: list[SubjectiveEpisode] = []
        if self._link_store is not None and episode_by_id:
            seeds = frozenset(episode_by_id.keys())
            priming = neighbor_priming_scores(
                player_id=player_id,
                seed_episode_ids=seeds,
                link_store=self._link_store,
                now=effective_now,
                max_hops=self._spreading_max_hops,
            )
            ranked = sorted(priming.items(), key=lambda t: t[1], reverse=True)
            for eid, _score in ranked[:limit_per_axis]:
                if eid in episode_by_id:
                    continue
                ep = self._store.get(player_id, eid)
                if ep is None:
                    continue
                episode_by_id[eid] = ep
                source_axes_by_episode[eid].add(PASSIVE_RECALL_AXIS_SPREADING)
                spreading_rows.append(ep)

        raw_counts: list[tuple[str, int]] = [(PASSIVE_RECALL_AXIS_TEMPORAL, len(temporal_rows))]
        raw_counts.extend((lab, len(rows)) for lab, rows, _g in cue_arms)
        if spreading_rows:
            raw_counts.append((PASSIVE_RECALL_AXIS_SPREADING, len(spreading_rows)))

        union_before_cap = len(episode_by_id)

        arms: list[tuple[str, list[SubjectiveEpisode]]] = [(PASSIVE_RECALL_AXIS_TEMPORAL, temporal_rows)]
        arms.extend((lab, rows) for lab, rows, _g in cue_arms)
        if spreading_rows:
            arms.append((PASSIVE_RECALL_AXIS_SPREADING, spreading_rows))

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
