"""Episode store から受動想起用候補を、時間軸と cue 軸の和集合で取る純粋ロジック（prompt / LLM 未接続）。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import MemoryLinkRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.llm.services.episodic_spreading_activation import (
    neighbor_priming_scores,
)
from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
    IEpisodicRecallHabituationStore,
    compute_habituation_penalty,
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
    EpisodicEpisodeRepository の並び（occurred_at 降順、同一時刻は episode_id 降順）と整合するキー。
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
    store: EpisodicEpisodeRepository,
    player_id: int,
    *,
    bucket: str,
    cues: Sequence[EpisodicCue],
    limit_per_axis: int,
    being_id: Optional[BeingId] = None,
    min_occurred_at: Optional[datetime] = None,
) -> tuple[
    str,
    list[SubjectiveEpisode],
    dict[str, frozenset[str]],
    dict[str, frozenset[str]],
]:
    """
    単一論理バケツ内で list_by_cue を統合する。
    place ファミリーはラウンドロビン・ラベルが cue:place_family、ソースは cue:{axis} のまま。
    object および place は粒度の高い一致を arm 内の並びで優先する。

    返り値 4 番目の ``cue_keys_by_ep`` は、各 episode がこの bucket 内で
    マッチした EpisodicCue の canonical 形 (``axis:value``) の集合。
    PR6 (R3) の cross-bucket スコアリングで使う。
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
    cue_keys_by_ep: dict[str, set[str]] = defaultdict(set)
    max_gran: dict[str, float] = defaultdict(float)

    # PR6 (R3): 個別 cue の fetch は ``limit_per_axis * len(cues)`` まで広げる。
    # こうしないと「ある cue の top N からだけ漏れた multi-match episode」が
    # 別の cue の query で再発見されても within-bucket cue hit 数が 1 のまま
    # になり、上位化されない。最終的に bucket 単位で ``limit_per_axis`` まで
    # 切り直すため、外向きの contract は変えない。
    per_cue_fetch_limit = max(limit_per_axis, limit_per_axis * len(cues))

    for cue in cues:
        ax_label = passive_recall_cue_axis_source_label(cue)
        cue_canonical = cue.to_canonical()
        if bucket == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY:
            g_weight = passive_recall_place_axis_granularity_weight(cue.axis)
        elif cue.axis == "object":
            g_weight = passive_recall_object_value_granularity_weight(cue.value)
        else:
            g_weight = 0.0

        # Phase 3 Step 3e-3: legacy 撤去済。being_id 未解決時は空 list で
        # graceful fallback (= prompt 強化が痩せるだけで turn は止めない)。
        if being_id is None:
            cue_episodes: list[SubjectiveEpisode] = []
        else:
            cue_episodes = store.list_by_cue_by_being(
                being_id,
                cue,
                per_cue_fetch_limit,
                min_occurred_at=min_occurred_at,
            )
        for ep in cue_episodes:
            eid = ep.episode_id
            merged[eid] = ep
            labels_by_ep[eid].add(ax_label)
            cue_keys_by_ep[eid].add(cue_canonical)
            if use_quality:
                max_gran[eid] = max(max_gran[eid], g_weight)

    def arm_sort_key(ep: SubjectiveEpisode) -> tuple[int, float, datetime, str]:
        # PR6 (R3): within-bucket での distinct cue マッチ数を最優先キーに乗せる。
        # これにより「同 bucket 内で複数 cue 値にマッチした episode」が
        # limit_per_axis の切断より前に上位化される (cross-bucket 分の score は
        # bucket fetch 後に retrieve() 側で再計算するが、cross-bucket での
        # 加点が limit に阻まれて反映できないケースは「両 bucket とも
        # limit_per_axis に収まる」前提に依存する — 通常運用の limit は
        # 充分大きく、現状その想定で OK)。
        bucket_cue_hits = len(cue_keys_by_ep.get(ep.episode_id, ()))
        gran = max_gran[ep.episode_id] if use_quality else 0.0
        dt, eid = _occurrence_sort_key(ep)
        return (bucket_cue_hits, gran, dt, eid)

    ordered = sorted(merged.values(), key=arm_sort_key, reverse=True)
    if limit_per_axis > 0:
        ordered = ordered[:limit_per_axis]

    labels_frozen = {eid: frozenset(ls) for eid, ls in labels_by_ep.items()}
    cue_keys_frozen = {eid: frozenset(ks) for eid, ks in cue_keys_by_ep.items()}
    return rr_label, ordered, labels_frozen, cue_keys_frozen


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
    """#526 後続 段階 2: 慣化ペナルティが適用された episode の (id, penalty)。
    penalty=0 のものや habituation off 時は空 tuple。post-hoc で「どの episode
    がどれだけ沈んだか」を計測できる。"""
    habituation_penalty_by_episode: tuple[tuple[str, int], ...] = ()


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
        store: EpisodicEpisodeRepository,
        *,
        link_store: MemoryLinkRepository | None = None,
        spreading_max_hops: int = 2,
        being_attachment_resolver: Optional[BeingAttachmentResolver] = None,
        default_world_id: Optional[WorldId] = None,
        habituation_store: Optional[IEpisodicRecallHabituationStore] = None,
        habituation_decay_window_ticks: int = 5,
    ) -> None:
        # Phase 3 Step 3c-3: legacy player_id 経路は撤去済。Resolver+WorldId が
        # 未注入 / Being 未 provision の場合は spreading 軸を skip
        # (= prompt 強化が痩せるだけで turn は止めない graceful fallback)。
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, WorldId):
            raise TypeError("default_world_id must be WorldId")
        if not isinstance(habituation_decay_window_ticks, int) or isinstance(
            habituation_decay_window_ticks, bool
        ):
            raise TypeError("habituation_decay_window_ticks must be int")
        if habituation_decay_window_ticks < 0:
            raise ValueError(
                "habituation_decay_window_ticks must be 0 or greater"
            )
        self._store = store
        self._link_store = link_store
        self._spreading_max_hops = spreading_max_hops
        self._resolver = being_attachment_resolver
        self._default_world_id = default_world_id
        # #526 段階 2: 慣化ペナルティ。store 未注入なら penalty 計算 skip
        # (= default off で既存挙動と完全同一)。
        self._habituation_store = habituation_store
        self._habituation_decay_window_ticks = habituation_decay_window_ticks

    def _resolve_being_id(self, player_id: int) -> Optional[BeingId]:
        """dual-path: Resolver+WorldId 揃いつつ Being が attach 済なら BeingId、
        いずれか欠ければ None (= legacy 経路へ fallback)。"""
        if self._resolver is None or self._default_world_id is None:
            return None
        return self._resolver.resolve_being_id(
            self._default_world_id, PlayerId(player_id)
        )

    def retrieve(
        self,
        *,
        player_id: int,
        situation_cues: Sequence[EpisodicCue],
        limit_per_axis: int,
        max_candidates: int,
        now: datetime | None = None,
        min_occurred_at: datetime | None = None,
        current_tick: Optional[int] = None,
    ) -> EpisodicPassiveRecallRetrievalResult:
        """過去 episode を situation cues に基づいて recall する。

        PR5 (R1): ``min_occurred_at`` が与えられたとき、temporal / cue 軸とも
        その時刻より厳密に古い episode のみを対象にする (= sliding window に
        まだ生きている直近 episode を recall から排除)。
        PR5 (R2): temporal 軸は **situation_cues が空のときのみ** 発火する
        fallback として動かす。cue が立つ通常 turn では「直近の出来事」を
        recall に紛れ込ませない。

        #526 段階 2: ``current_tick`` と ``habituation_store`` が両方揃った
        とき、直近で recall された episode に慣化ペナルティを score から引く。
        どちらかが欠ければ penalty 計算は skip し既存挙動を保つ。
        ``record_recall`` (= sidecar への書込) はこの service ではなく
        呼び出し側 (prompt_builder) が candidates 確定後に行う。retrieve
        自身は副作用なしを保つ。
        """
        # Phase 3 Step 3e-3: legacy 経路は撤去済。Being 未解決時は temporal/cue
        # 軸も空になる graceful fallback (= prompt 強化が痩せるだけで turn は
        # 止めない)。spreading 軸の skip と挙動を揃える。
        being_id = self._resolve_being_id(player_id)

        # R2: temporal 軸の発火条件。cue が立っている通常 turn では skip し、
        # cue が一切無い idle 等の状況でのみ「直近の出来事」を fallback として
        # 引く。R1 の min_occurred_at と合わせれば、そのときも sliding window
        # 範囲外のものだけが拾われる。
        temporal_axis_enabled = len(situation_cues) == 0
        if being_id is None or not temporal_axis_enabled:
            temporal_rows: list[SubjectiveEpisode] = []
        else:
            temporal_rows = self._store.list_recent_by_being(
                being_id, limit_per_axis, min_occurred_at=min_occurred_at
            )

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

        cue_arms: list[
            tuple[
                str,
                list[SubjectiveEpisode],
                dict[str, frozenset[str]],
                dict[str, frozenset[str]],
            ]
        ] = []
        for bucket in axis_order:
            cues = axis_to_cues[bucket]
            rr_label, rows, granular, cue_keys = _merged_ordered_episodes_for_cue_bucket(
                self._store,
                player_id,
                bucket=bucket,
                cues=cues,
                limit_per_axis=limit_per_axis,
                being_id=being_id,
                min_occurred_at=min_occurred_at,
            )
            cue_arms.append((rr_label, rows, granular, cue_keys))

        # PR6 (R3): cross-bucket での cue マッチ数を episode 単位で集計する。
        # 同一 episode が複数 bucket (= 別 axis ファミリー) の cue にヒット
        # していれば、その distinct canonical 数 (axis:value) を score とする。
        # 各 cue arm の rows を score 降順に stable sort (= 同点は bucket 内
        # の既存順 = within-bucket cue hit 数 + granularity + occurred_at を
        # 保つ)。
        #
        # NOTE: temporal / spreading 軸の rows は cue マッチ由来ではないため
        # ここでは並べ替えない (= multi_cue_canonicals は cue_arms 由来のみで
        # 集計し、temporal / spreading 軸の episode の score は 0 になる)。
        # 実運用上の整合性: R2 で temporal は cue 不在時のみ発火し、spreading
        # は cue を seed にした派生のため、両者と cue が同一 episode を
        # 出すことは稀。
        multi_cue_canonicals: dict[str, frozenset[str]] = {}
        accum: dict[str, set[str]] = defaultdict(set)
        for _label, _rows, _granular, cue_keys in cue_arms:
            for eid, keys in cue_keys.items():
                accum[eid].update(keys)
        for eid, keys in accum.items():
            multi_cue_canonicals[eid] = frozenset(keys)

        def multi_cue_score(eid: str) -> int:
            return len(multi_cue_canonicals.get(eid, frozenset()))

        # #526 段階 2: 慣化ペナルティ。store 注入 + current_tick 指定が
        # 揃ったときだけ計算し、score から減算する。条件が欠ければ
        # 0 ペナルティで既存挙動を保つ (= silent fallback ではなく明示的に
        # 「current_tick が無いから慣化は使えない」状態を返す)。
        habituation_active = (
            self._habituation_store is not None
            and current_tick is not None
            and self._habituation_decay_window_ticks > 0
            and being_id is not None
        )
        habituation_penalty_records: dict[str, int] = {}

        def habituation_penalty(eid: str) -> int:
            if not habituation_active:
                return 0
            # mypy 緩和: habituation_active=True なら以下は非 None
            assert self._habituation_store is not None
            assert current_tick is not None
            assert being_id is not None
            last = self._habituation_store.get_last_recalled_tick(being_id, eid)
            return compute_habituation_penalty(
                last_recalled_tick=last,
                current_tick=current_tick,
                decay_window=self._habituation_decay_window_ticks,
            )

        def _arm_score_key(ep: SubjectiveEpisode) -> int:
            penalty = habituation_penalty(ep.episode_id)
            if penalty > 0:
                # debug 用に記録 (penalty=0 は記録しない)。同 episode が複数
                # arm で評価されても結果は同じなので dict で上書き OK。
                habituation_penalty_records[ep.episode_id] = penalty
            return multi_cue_score(ep.episode_id) - penalty

        cue_arms = [
            (label, sorted(rows, key=_arm_score_key, reverse=True), granular, cue_keys)
            for label, rows, granular, cue_keys in cue_arms
        ]

        episode_by_id: dict[str, SubjectiveEpisode] = {}
        source_axes_by_episode: dict[str, set[str]] = defaultdict(set)

        for ep in temporal_rows:
            episode_by_id[ep.episode_id] = ep
            source_axes_by_episode[ep.episode_id].add(PASSIVE_RECALL_AXIS_TEMPORAL)

        for _, rows, granular, _ in cue_arms:
            for ep in rows:
                eid = ep.episode_id
                episode_by_id[eid] = ep
                for ax in granular.get(eid, ()):
                    source_axes_by_episode[eid].add(ax)

        effective_now = now if now is not None else datetime.now(timezone.utc)
        spreading_rows: list[SubjectiveEpisode] = []
        if self._link_store is not None and episode_by_id and being_id is not None:
            # Phase 3 Step 3c-3: spreading activation は being_id keyed only。
            # Being 未解決時は spreading 軸を skip (= prompt 強化が痩せるだけで
            # turn は止めない)。
            seeds = frozenset(episode_by_id.keys())
            priming = neighbor_priming_scores(
                being_id=being_id,
                seed_episode_ids=seeds,
                link_store=self._link_store,
                now=effective_now,
                max_hops=self._spreading_max_hops,
            )
            ranked = sorted(priming.items(), key=lambda t: t[1], reverse=True)
            for eid, _score in ranked[:limit_per_axis]:
                if eid in episode_by_id:
                    continue
                # being_id がここまで来ているなら必ず非 None (= 上記 if で確認済)
                ep = self._store.get_by_being(being_id, eid)
                if ep is None:
                    continue
                episode_by_id[eid] = ep
                source_axes_by_episode[eid].add(PASSIVE_RECALL_AXIS_SPREADING)
                spreading_rows.append(ep)

        raw_counts: list[tuple[str, int]] = [(PASSIVE_RECALL_AXIS_TEMPORAL, len(temporal_rows))]
        raw_counts.extend((lab, len(rows)) for lab, rows, _g, _k in cue_arms)
        if spreading_rows:
            raw_counts.append((PASSIVE_RECALL_AXIS_SPREADING, len(spreading_rows)))

        union_before_cap = len(episode_by_id)

        arms: list[tuple[str, list[SubjectiveEpisode]]] = [(PASSIVE_RECALL_AXIS_TEMPORAL, temporal_rows)]
        arms.extend((lab, rows) for lab, rows, _g, _k in cue_arms)
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

        habituation_payload = tuple(
            sorted(habituation_penalty_records.items(), key=lambda t: t[0])
        )
        debug = EpisodicPassiveRecallRetrievalDebug(
            raw_row_count_by_axis=tuple(raw_counts),
            union_episode_count_before_max_cap=union_before_cap,
            candidate_episode_sources=tuple(candidate_sources),
            final_episode_count_by_source_axis=final_axis_counts,
            habituation_penalty_by_episode=habituation_payload,
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
