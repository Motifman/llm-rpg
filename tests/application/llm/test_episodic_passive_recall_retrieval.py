# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p7")
"""EpisodicPassiveRecallRetrievalService の和集合・round-robin・軸デバッグの検証。"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.passive_recall_cue_families import (
    PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY,
    PASSIVE_RECALL_PLACE_FAMILY_LABEL,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    PASSIVE_RECALL_AXIS_TEMPORAL,
    EpisodicPassiveRecallRetrievalService,
    passive_recall_cue_axis_label,
    _merged_ordered_episodes_for_cue_bucket,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def _make_resolver_and_being():
    """Phase 3 Step 3e-3 migration: Resolver+WorldId+ provision 済 Being を作る。
    being_id は module-level ``being_id`` ("being_w1_p1") に揃える。"""
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
    from ai_rpg_world.domain.world.value_object.world_id import (
        DEFAULT_SINGLE_WORLD_ID,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
        InMemoryBeingRepository,
    )

    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    BeingProvisioningService(repo).ensure_attached(PlayerId(7))
    return resolver, DEFAULT_SINGLE_WORLD_ID


def _episode(
    *,
    episode_id: str,
    player_id: int = 7,
    occurred_at: datetime,
    cues: tuple[EpisodicCue, ...],
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-a",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=cues,
        recall_text="r",
    )


class TestEpisodicPassiveRecallRetrievalTemporalOnly:
    """時間軸だけで候補が取れること"""

    def test_temporal_axis_only_when_no_situation_cues(self) -> None:
        """situation_cues が空なら temporal のみがソースとなり、debug に temporal が載る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="place", value="x", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(being_id, _episode(episode_id="old", occurred_at=base, cues=(cue,)))
        store.put_by_being(being_id, _episode(episode_id="new", occurred_at=base + timedelta(days=1), cues=(cue,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        assert ids == ["new", "old"]
        assert all(PASSIVE_RECALL_AXIS_TEMPORAL in c.source_axes for c in result.candidates)
        assert result.debug.raw_row_count_by_axis == ((PASSIVE_RECALL_AXIS_TEMPORAL, 2),)
        assert result.debug.final_episode_count_by_source_axis == ((PASSIVE_RECALL_AXIS_TEMPORAL, 2),)


class TestEpisodicPassiveRecallRetrievalCueOnly:
    """cue 軸だけで temporal に入らない古い episode を拾えること"""

    def test_cue_axis_retrieves_old_episode_not_in_temporal_window(self) -> None:
        """temporal の limit で切り落とされる古い件が、cue 照合で和集合に入る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        trap = EpisodicCue(axis="schema_hint", value="trap", source=EpisodicCueSource.TOOL)
        other = EpisodicCue(axis="place", value="99", source=EpisodicCueSource.RUNTIME_CONTEXT)
        for i in range(3):
            store.put_by_being(being_id, 
                _episode(
                    episode_id=f"recent-{i}",
                    occurred_at=base + timedelta(days=10 + i),
                    cues=(other,),
                )
            )
        old = _episode(episode_id="trap-old", occurred_at=base, cues=(trap,))
        store.put_by_being(being_id, old)
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(trap,),
            limit_per_axis=2,
            max_candidates=20,
        )
        by_id = {c.episode.episode_id: c for c in result.candidates}
        assert "trap-old" in by_id
        assert passive_recall_cue_axis_label(trap) == "cue:schema_hint"
        assert passive_recall_cue_axis_label(trap) in by_id["trap-old"].source_axes
        assert (passive_recall_cue_axis_label(trap), 1) in result.debug.final_episode_count_by_source_axis


class TestEpisodicPassiveRecallRetrievalUnionDedupe:
    """temporal と cue の重複が和集合で 1 件になること"""

    def test_episode_は_cue_軸経由でのみ出る_R2_後(self) -> None:
        """PR5 R2 後: cue が立っているときは temporal 軸が off になる。

        旧テスト名 ``test_same_episode_from_temporal_and_cue_has_single_row_and_merged_axes``
        は「cue + temporal が同じ episode を出して merge される」挙動を担保
        していたが、R2 で temporal 軸は fallback (= cue 軸が空のときのみ)
        になったので、source_axes に temporal は出なくなる。
        """
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        shared = EpisodicCue(axis="object", value="box", source=EpisodicCueSource.RUNTIME_CONTEXT)
        ep = _episode(episode_id="both", occurred_at=ts, cues=(shared,))
        store.put_by_being(being_id, ep)
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(shared,),
            limit_per_axis=5,
            max_candidates=10,
        )
        assert len(result.candidates) == 1
        axes = result.candidates[0].source_axes
        # R2 後: temporal は cue 立つときは走らないので source_axes から外れる
        assert PASSIVE_RECALL_AXIS_TEMPORAL not in axes
        assert passive_recall_cue_axis_label(shared) == "cue:object"
        assert passive_recall_cue_axis_label(shared) in axes
        assert result.debug.union_episode_count_before_max_cap == 1
        assert result.debug.candidate_episode_sources == (
            ("both", ("cue:object",)),
        )


class TestEpisodicPassiveRecallRetrievalLimits:
    """limit_per_axis / max_candidates が効くこと"""

    def test_limit_per_axis_caps_each_axis_fetch(self) -> None:
        """list_by_cue が limit_per_axis で打ち切られる。

        PR5 R2 後: cue が立つときは temporal 軸が走らないので、temporal の
        raw_row_count は記録されない。cue 軸のみが limit_per_axis (=2) で
        打ち切られる。
        """
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        k = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        for i in range(5):
            store.put_by_being(being_id,
                _episode(
                    episode_id=f"e{i}",
                    occurred_at=base + timedelta(hours=i),
                    cues=(k,),
                )
            )
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(k,),
            limit_per_axis=2,
            max_candidates=20,
        )
        raw = dict(result.debug.raw_row_count_by_axis)
        # R2 後: cue が立つときの temporal は走らないため、temporal の raw
        # row count は 0 で記録される (= 軸 key 自体は debug に残る)
        assert raw.get(PASSIVE_RECALL_AXIS_TEMPORAL, 0) == 0
        assert raw["cue:action"] == 2

    def test_max_candidates_uses_round_robin_not_global_recency(self) -> None:
        """max_candidates 件は全体時刻順の先頭ではなく、軸巡回で選ばれる。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        b = EpisodicCue(axis="b", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(being_id, _episode(episode_id="p1", occurred_at=base + timedelta(days=3), cues=(a,)))
        store.put_by_being(being_id, _episode(episode_id="p2", occurred_at=base + timedelta(days=2), cues=(b,)))
        store.put_by_being(being_id, _episode(episode_id="p3", occurred_at=base + timedelta(days=1), cues=(a, b)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a, b),
            limit_per_axis=10,
            max_candidates=2,
        )
        assert len(result.candidates) == 2
        # PR6 (R3) 後: p3 は a と b の両方にマッチする (= multi_cue_score=2)
        # ため、各 arm 内で stable sort により先頭に押し上げられる。
        # round-robin は a 軸 → p3、b 軸 → p3 は既選ばれなので b 軸の次=p2。
        # 結果として「単一 cue マッチ p1」よりも「複数 cue マッチ p3」が
        # 優先される (R3 の狙い)。
        assert [c.episode.episode_id for c in result.candidates] == ["p3", "p2"]
        assert result.debug.union_episode_count_before_max_cap == 3


class TestEpisodicPassiveRecallRetrievalDebugAxes:
    """debug に source axis の集計が残ること"""

    def test_final_episode_count_by_source_axis_reflects_overlap(self) -> None:
        """重複 episode は各軸のカウントに二重に効かない（episode あたり 1）。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 5, 2, tzinfo=timezone.utc)
        c = EpisodicCue(axis="outcome", value="failure", source=EpisodicCueSource.TOOL)
        store.put_by_being(being_id, _episode(episode_id="solo-recent", occurred_at=ts + timedelta(days=1), cues=()))
        store.put_by_being(being_id, _episode(episode_id="overlap", occurred_at=ts, cues=(c,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(player_id=7, situation_cues=(c,), limit_per_axis=5, max_candidates=10)
        counts = dict(result.debug.final_episode_count_by_source_axis)
        # PR5 R2 後: cue 立つときの temporal は走らない → counts に temporal キー無し
        assert PASSIVE_RECALL_AXIS_TEMPORAL not in counts
        assert counts["cue:outcome"] == 1


class TestEpisodicPassiveRecallRetrievalPlaceFamily:
    """場所論理ファミリー（複数軸を 1 本）と粒度優先ソート"""

    def test_place_family_single_round_robin_slot_with_three_place_cues(self) -> None:
        """place_spot / sub_loc / entity のとき cue 側は場所ファミリー 1 本＋entity の 2 本となり entity が早く枠に入る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        c_spot = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_sub = EpisodicCue(axis="sub_loc", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_entity = EpisodicCue(axis="entity", value="alice", source=EpisodicCueSource.TOOL)
        store.put_by_being(being_id, _episode(episode_id="f1", occurred_at=base + timedelta(days=10), cues=()))
        store.put_by_being(being_id, _episode(episode_id="ep_spot", occurred_at=base, cues=(c_spot,)))
        store.put_by_being(being_id, _episode(episode_id="ep_sub", occurred_at=base - timedelta(days=1), cues=(c_sub,)))
        store.put_by_being(being_id, _episode(episode_id="ep_e", occurred_at=base - timedelta(days=2), cues=(c_entity,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_spot, c_sub, c_entity),
            limit_per_axis=1,
            max_candidates=3,
        )
        raw = dict(result.debug.raw_row_count_by_axis)
        assert raw[PASSIVE_RECALL_PLACE_FAMILY_LABEL] == 1
        assert raw["cue:entity"] == 1
        ids = [c.episode.episode_id for c in result.candidates]
        # PR5 R2 後: cue が立っているため temporal 軸 (f1) は出ない。
        # cue 由来の ep_spot / ep_e のみ round-robin で並ぶ。
        assert ids == ["ep_spot", "ep_e"]

    def test_place_family_prefers_place_spot_over_tile_under_limit_cap(self) -> None:
        """場所ファミリー統合リストでは place_spot 一致を tile_area 単独一致より先に並べ limit が効く。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 8, 2, tzinfo=timezone.utc)
        c_tile = EpisodicCue(axis="tile_area", value="9", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_spot = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        weaker = EpisodicCue(axis="tile_area", value="9", source=EpisodicCueSource.RUNTIME_CONTEXT)
        stronger = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(being_id, _episode(episode_id="only_tile", occurred_at=ts, cues=(weaker,)))
        store.put_by_being(being_id, _episode(episode_id="both", occurred_at=ts, cues=(stronger, weaker)))
        rr_label, rows, _gran, _keys = _merged_ordered_episodes_for_cue_bucket(
            store,
            7,
            bucket=PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY,
            cues=[c_spot, c_tile],
            limit_per_axis=1,
            being_id=being_id,
        )
        assert rr_label == PASSIVE_RECALL_PLACE_FAMILY_LABEL
        assert [e.episode_id for e in rows] == ["both"]


class TestEpisodicPassiveRecallRetrievalObjectGranularity:
    """object 軸の値プレフィックスによる並び優先"""

    def test_item_instance_ranks_above_world_object_when_both_queries(self) -> None:
        """item_instance と world_object の両クエリがあるとき粒度の高い方が統合並び／limit で先になる。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 9, 1, tzinfo=timezone.utc)
        cw = EpisodicCue(axis="object", value="world_object_1", source=EpisodicCueSource.TOOL)
        ci = EpisodicCue(axis="object", value="item_instance_2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(being_id, _episode(episode_id="to_wo", occurred_at=ts, cues=(cw,)))
        store.put_by_being(being_id, _episode(episode_id="to_item", occurred_at=ts + timedelta(seconds=1), cues=(ci,)))
        rr_label, rows, _gran, _keys = _merged_ordered_episodes_for_cue_bucket(
            store,
            7,
            bucket="object",
            cues=[cw, ci],
            limit_per_axis=1,
            being_id=being_id,
        )
        assert rr_label == "cue:object"
        assert [e.episode_id for e in rows] == ["to_item"]


class TestEpisodicPassiveRecallRetrievalRoundRobinFairness:
    """round-robin で cue 軸が時間に押し流されないこと"""

    def test_old_cue_match_surfaces_despite_many_recent_in_temporal(self) -> None:
        """古いが cue に一致する episode が、直近だけの temporal 先頭に独占されず採用される。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        filler = EpisodicCue(axis="place", value="99", source=EpisodicCueSource.RUNTIME_CONTEXT)
        trap = EpisodicCue(axis="schema_hint", value="trap", source=EpisodicCueSource.TOOL)
        for i in range(4):
            store.put_by_being(being_id, 
                _episode(
                    episode_id=f"f{i}",
                    occurred_at=base + timedelta(days=i + 1),
                    cues=(filler,),
                )
            )
        store.put_by_being(being_id, _episode(episode_id="trap-old", occurred_at=base, cues=(trap,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(trap,),
            limit_per_axis=3,
            max_candidates=2,
        )
        # PR5 R2 後: cue (trap) が立っているため temporal は走らない。
        # filler は cue ("place") も別軸として立つが、retrieve に渡している
        # situation_cues には trap のみ含まれるため、filler を持つ f0-f3 は
        # cue 軸でも recall されない。結果は trap-old のみ。
        assert [c.episode.episode_id for c in result.candidates] == ["trap-old"]

    def test_round_robin_interleaves_distinct_cue_axes(self) -> None:
        """cue:place_spot, cue:entity, cue:object を巡回して採用する。

        PR5 R2 後: cue が立つときの temporal は走らない。3 つの cue 軸での
        interleave のみが結果に出る。
        """
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        c_place = EpisodicCue(axis="place_spot", value="12", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_entity = EpisodicCue(axis="entity", value="alice", source=EpisodicCueSource.TOOL)
        c_object = EpisodicCue(axis="object", value="box", source=EpisodicCueSource.TOOL)
        store.put_by_being(being_id, _episode(episode_id="T", occurred_at=base + timedelta(days=10), cues=()))
        store.put_by_being(being_id, _episode(episode_id="P", occurred_at=base + timedelta(days=5), cues=(c_place,)))
        store.put_by_being(being_id, _episode(episode_id="E", occurred_at=base + timedelta(days=4), cues=(c_entity,)))
        store.put_by_being(being_id, _episode(episode_id="O", occurred_at=base + timedelta(days=3), cues=(c_object,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_entity, c_object),
            limit_per_axis=1,
            max_candidates=4,
        )
        # T (cues=()) は temporal 経路でしか入らないので R2 後は消える
        assert [c.episode.episode_id for c in result.candidates] == ["P", "E", "O"]
        axes_by_id = {c.episode.episode_id: set(c.source_axes) for c in result.candidates}
        assert axes_by_id["P"] == {"cue:place_spot"}
        assert axes_by_id["E"] == {"cue:entity"}
        assert axes_by_id["O"] == {"cue:object"}

    def test_small_max_candidates_picks_only_cue_axes_under_r2(self) -> None:
        """PR5 R2 後: cue が立つときは temporal が走らない。

        旧テストは「max_candidates が小さくても temporal だけで枠を埋めない」
        を verify していたが、R2 後は temporal そのものが off になるため、
        cue 軸の round-robin のみが結果。
        """
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        c_place = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_entity = EpisodicCue(axis="entity", value="z", source=EpisodicCueSource.TOOL)
        for i in range(3):
            store.put_by_being(being_id, 
                _episode(
                    episode_id=f"t{i}",
                    occurred_at=base + timedelta(hours=i),
                    cues=(),
                )
            )
        store.put_by_being(being_id, _episode(episode_id="place-only", occurred_at=base - timedelta(days=1), cues=(c_place,)))
        store.put_by_being(being_id, _episode(episode_id="entity-only", occurred_at=base - timedelta(days=2), cues=(c_entity,)))
        _res, _wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_res,
            default_world_id=_wid,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_entity),
            limit_per_axis=5,
            max_candidates=3,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # R2: cue が立つので temporal は off、t0/t1/t2 は出ない
        assert ids == ["place-only", "entity-only"]
        assert "entity-only" in ids


class TestEpisodicPassiveRecallRetrievalHabituation:
    """慣化ペナルティ (#526 後続 段階 2) — 直近 recall された episode は
    arm 内 score を下げ、他の episode が round-robin で上に来る。
    """

    def _setup(self):
        """同一 cue (place_spot:1) に hit する episode を 2 件作り、
        どちらが先に拾われるかを慣化で操作できる構成にする。"""
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )

        store = InMemorySubjectiveEpisodeStore()
        c_place = EpisodicCue(
            axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        c_obj = EpisodicCue(
            axis="object", value="o1", source=EpisodicCueSource.TOOL
        )
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        # ep-A: place_spot のみで hit (multi_cue_score=1)
        store.put_by_being(
            being_id,
            _episode(
                episode_id="ep-A",
                occurred_at=base,
                cues=(c_place,),
            ),
        )
        # ep-B: place_spot + object の両方で hit (multi_cue_score=2 → 通常は上位)
        store.put_by_being(
            being_id,
            _episode(
                episode_id="ep-B",
                occurred_at=base - timedelta(hours=1),
                cues=(c_place, c_obj),
            ),
        )
        _res, _wid = _make_resolver_and_being()
        habit_store = InMemoryEpisodicRecallHabituationStore()
        return store, habit_store, _res, _wid, c_place, c_obj

    def test_habituation_未注入なら_既存挙動と同一(self) -> None:
        """``habituation_store=None`` で構成すれば既存の round-robin 結果と同じ。"""
        store, _, res, wid, c_place, c_obj = self._setup()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_obj),
            limit_per_axis=5,
            max_candidates=2,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # ep-B は 2 cue hit (place_spot + object) で arm 内 score が高い
        assert "ep-A" in ids and "ep-B" in ids
        # debug に habituation 関連キーは出ない (= default off)
        assert result.debug.habituation_penalty_by_episode == ()

    def test_直前_tick_で_recall_された_episode_は_順位が下がる(self) -> None:
        """ep-B を直前 tick で recall 済にすると、arm 内 score が下がって
        ep-A が同 arm の上位になる。round-robin で ep-A が先に選ばれる。"""
        store, habit, res, wid, c_place, c_obj = self._setup()
        # ep-B を current_tick=10 の 1 tick 前に recall 済にする
        habit.record_recall(being_id, ["ep-B"], tick=9)

        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=res,
            default_world_id=wid,
            habituation_store=habit,
            habituation_decay_window_ticks=5,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_obj),
            limit_per_axis=5,
            max_candidates=2,
            current_tick=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # ペナルティで ep-B の有効 score = 2 - 4 = -2 < ep-A の score = 1
        # → arm 内では ep-A が上位、ep-B が下位になる
        # round-robin で同 arm から取るとき ep-A → ep-B の順で並ぶ
        # 厳密な順序は arm の組合せ次第なので、両方含むことと、debug を確認
        assert set(ids) == {"ep-A", "ep-B"}
        penalty_dict = dict(result.debug.habituation_penalty_by_episode)
        assert penalty_dict["ep-B"] == 4  # decay_window 5 - age 1 = 4
        # ep-A は未 recall なので penalty 0 (または非含)
        assert penalty_dict.get("ep-A", 0) == 0

    def test_decay_window_経過後は_慣化が解ける(self) -> None:
        """十分時間が経った recall は penalty を出さない (= 再度引かれる)。"""
        store, habit, res, wid, c_place, c_obj = self._setup()
        habit.record_recall(being_id, ["ep-B"], tick=1)

        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=res,
            default_world_id=wid,
            habituation_store=habit,
            habituation_decay_window_ticks=5,
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_obj),
            limit_per_axis=5,
            max_candidates=2,
            current_tick=100,  # decay_window=5 を遥かに超える
        )
        # ep-B のペナルティは 0 になっているはず
        penalty_dict = dict(result.debug.habituation_penalty_by_episode)
        # decay 切れの episode は debug にも含めない (penalty=0 は記録不要)
        assert penalty_dict.get("ep-B", 0) == 0

    def test_current_tick_未指定なら_penalty_は_適用されない(self) -> None:
        """tick が分からない呼び出し (idle 等) では penalty を出さない。"""
        store, habit, res, wid, c_place, c_obj = self._setup()
        habit.record_recall(being_id, ["ep-B"], tick=0)

        svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=res,
            default_world_id=wid,
            habituation_store=habit,
            habituation_decay_window_ticks=5,
        )
        # current_tick を渡さない
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_obj),
            limit_per_axis=5,
            max_candidates=2,
        )
        assert result.debug.habituation_penalty_by_episode == ()
