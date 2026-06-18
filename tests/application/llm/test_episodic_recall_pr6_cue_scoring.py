# Phase 3 Step 3e-3 bulk migration: 本テストでも Resolver+WorldId+provision 済
# Being を作って retrieve に渡す。being_id は module-level で固定する。
"""PR6 (R3): cue マッチ数による episode 並べ替えの検証。

R3 の狙い: 単一 cue にしかマッチしない episode より、複数 cue (同 bucket /
別 bucket とも) に同時にマッチした episode を上位に出す。round-robin で各
arm から拾うとき、arm 内で stable sort によって multi-match が先頭に来る。
"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


being_id = BeingId("being_w1_p7")


def _make_resolver_and_being():
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
    occurred_at: datetime,
    cues: tuple[EpisodicCue, ...],
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=7,
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


class TestR3CrossBucketScoring:
    """R3: 別 bucket (axis) を跨いで複数 cue にマッチした episode が上位化される。"""

    def test_episode_matching_two_axes_outranks_single_axis_matches(self) -> None:
        """別 axis (a / b) 両方にマッチした古い episode が、各 arm で最新の単一マッチを抜く。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        b = EpisodicCue(axis="b", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        # newest = p1 (axis a のみ), p2 (axis b のみ), oldest = p3 (a と b 両方)
        store.put_by_being(
            being_id, _episode(episode_id="p1", occurred_at=base + timedelta(days=3), cues=(a,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="p2", occurred_at=base + timedelta(days=2), cues=(b,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="p3", occurred_at=base + timedelta(days=1), cues=(a, b))
        )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a, b),
            limit_per_axis=10,
            max_candidates=3,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # p3 が arm a と arm b の両方で先頭 → round-robin で最初に拾われる
        assert ids[0] == "p3"
        # 残り 2 件はそれぞれ単一マッチ。順序は問わない (round-robin の結果)
        assert set(ids[1:]) == {"p1", "p2"}

    def test_max_cap_2_prefers_multi_match_over_recent_single(self) -> None:
        """max_candidates=2 で打ち切られても、最新の単一マッチより multi-match が残る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        b = EpisodicCue(axis="b", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(
            being_id, _episode(episode_id="p1", occurred_at=base + timedelta(days=3), cues=(a,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="p2", occurred_at=base + timedelta(days=2), cues=(b,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="p3", occurred_at=base + timedelta(days=1), cues=(a, b))
        )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a, b),
            limit_per_axis=10,
            max_candidates=2,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # PR6 後: p3 (multi) が先頭固定。2 番目は round-robin で次の arm から
        # (a arm の次=p1 か b arm の次=p2 — round-robin の進み方で決まる)。
        assert ids[0] == "p3"
        assert len(ids) == 2
        assert ids[1] in {"p1", "p2"}

    def test_no_overlap_keeps_recency_order_within_each_arm(self) -> None:
        """全 episode が単一 cue にしかマッチしない場合は、既存の occurred_at 降順を維持する。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        b = EpisodicCue(axis="b", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put_by_being(
            being_id, _episode(episode_id="a-new", occurred_at=base + timedelta(days=3), cues=(a,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="a-old", occurred_at=base + timedelta(days=1), cues=(a,))
        )
        store.put_by_being(
            being_id, _episode(episode_id="b-new", occurred_at=base + timedelta(days=2), cues=(b,))
        )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a, b),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # arm a: [a-new, a-old] (recency), arm b: [b-new] — round-robin で
        # a-new → b-new → a-old。score は全部 1 なので並びは既存のまま。
        assert ids == ["a-new", "b-new", "a-old"]


class TestR3WithinBucketScoring:
    """R3: 同一 axis (bucket) 内で複数 cue 値にマッチした episode の上位化。"""

    def test_within_bucket_multi_value_match_outranks_single_value(self) -> None:
        """同じ axis で 2 つの value 両方にマッチした episode が、片方だけの新しい episode より上位。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        # entity 軸の 2 つの異なる値: alice / bob
        alice = EpisodicCue(axis="entity", value="alice", source=EpisodicCueSource.RUNTIME_CONTEXT)
        bob = EpisodicCue(axis="entity", value="bob", source=EpisodicCueSource.RUNTIME_CONTEXT)
        # newest = alice のみ、oldest = alice & bob 両方
        store.put_by_being(
            being_id,
            _episode(episode_id="solo", occurred_at=base + timedelta(days=2), cues=(alice,)),
        )
        store.put_by_being(
            being_id,
            _episode(
                episode_id="multi", occurred_at=base + timedelta(days=1), cues=(alice, bob)
            ),
        )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(alice, bob),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        assert ids[0] == "multi"
        assert "solo" in ids


class TestR3WithinBucketBeatsLimitTruncation:
    """R3: within-bucket multi-match は limit_per_axis の切断より前に上位化される。"""

    def test_old_multi_match_survives_limit_when_newer_singletons_exist(self) -> None:
        """新しい単一マッチが 2 件 + 古い multi-match 1 件、limit_per_axis=2 でも古い multi が残る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        alice = EpisodicCue(axis="entity", value="alice", source=EpisodicCueSource.RUNTIME_CONTEXT)
        bob = EpisodicCue(axis="entity", value="bob", source=EpisodicCueSource.RUNTIME_CONTEXT)
        # bucket 'entity' 内: 新しい single 2 件 + 古い multi 1 件
        store.put_by_being(
            being_id,
            _episode(episode_id="new-1", occurred_at=base + timedelta(days=5), cues=(alice,)),
        )
        store.put_by_being(
            being_id,
            _episode(episode_id="new-2", occurred_at=base + timedelta(days=4), cues=(alice,)),
        )
        store.put_by_being(
            being_id,
            _episode(
                episode_id="old-multi",
                occurred_at=base + timedelta(days=1),
                cues=(alice, bob),
            ),
        )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        # limit_per_axis=2 でも、bucket 内の sort key が「within-bucket cue
        # hit 数」を最優先にしているため、old-multi (2 hits) が切断より前に
        # 先頭化される。
        result = svc.retrieve(
            player_id=7,
            situation_cues=(alice, bob),
            limit_per_axis=2,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        assert "old-multi" in ids
        assert ids[0] == "old-multi"


class TestR3StableSortTies:
    """R3: score が同点なら既存の granularity / occurred_at 順を維持する (stable sort)。"""

    def test_same_score_preserves_occurred_at_desc(self) -> None:
        """score が全件 1 なら、各 arm 内では occurred_at 降順が保たれる。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        # 全部単一マッチ = score 1 で同点
        for i, day in enumerate([5, 3, 1]):
            store.put_by_being(
                being_id,
                _episode(
                    episode_id=f"e{i}",
                    occurred_at=base + timedelta(days=day),
                    cues=(a,),
                ),
            )
        res, wid = _make_resolver_and_being()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a,),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # 全 score 同点 → arm 内は occurred_at 降順 (= e0, e1, e2)
        assert ids == ["e0", "e1", "e2"]
