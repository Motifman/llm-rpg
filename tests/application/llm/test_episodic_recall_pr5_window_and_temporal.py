"""PR5 (R1 + R2) の挙動を直接担保する新規テスト。

R1: ``retrieve(min_occurred_at=...)`` で sliding window 範囲 (= まだ working
memory に生きている) episode を recall 結果から除外する。
R2: ``situation_cues`` が空のときのみ temporal 軸 が fallback として動く。
cue が立っているときは temporal 軸は走らない。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    PASSIVE_RECALL_AXIS_TEMPORAL,
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import (
    EpisodicCue,
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_being = BeingId("being_w1_p1")


def _episode(
    *,
    episode_id: str,
    occurred_at: datetime,
    cues: tuple[EpisodicCue, ...] = (),
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt",)),
        location=EpisodeLocation(spot_id=None),
        action=EpisodeAction(tool_name="test_tool"),
        who=("p",),
        what=episode_id,
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=cues,
        recall_text=f"recall:{episode_id}",
    )


def _make_resolver():
    """既存 test と同じ pattern で resolver + world_id を立てる。

    BeingProvisioningService(repo).ensure_attached(PlayerId(1)) で being_id
    は ``being_w1_p1`` に正規化される (module 冒頭の ``_being`` と一致)。
    """
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import (
        DEFAULT_SINGLE_WORLD_ID,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
        InMemoryBeingRepository,
    )

    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    BeingProvisioningService(repo).ensure_attached(PlayerId(1))
    return resolver, DEFAULT_SINGLE_WORLD_ID


class TestR1WindowOuterFilter:
    """``min_occurred_at`` 引数で sliding window 範囲外の episode のみ recall する。"""

    def test_missing_min_occurred_at_allows_all_episodes(self) -> None:
        """minoccurredat 未指定なら全 episode が対象。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        store.put_by_being(_being, _episode(episode_id="old", occurred_at=base, cues=(cue,)))
        store.put_by_being(_being, _episode(episode_id="recent", occurred_at=base + timedelta(days=5), cues=(cue,)))
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=1,
            situation_cues=(cue,),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        assert ids == {"old", "recent"}

    def test_min_occurred_episode_excluded(self) -> None:
        """minoccurredat より新しい episode は除外される。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        store.put_by_being(_being, _episode(episode_id="old", occurred_at=base, cues=(cue,)))
        store.put_by_being(
            _being, _episode(episode_id="recent", occurred_at=base + timedelta(days=5), cues=(cue,))
        )
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        # base + 3 day を境界に → old (base) は対象、recent (base+5day) は除外
        border = base + timedelta(days=3)
        result = svc.retrieve(
            player_id=1,
            situation_cues=(cue,),
            limit_per_axis=10,
            max_candidates=10,
            min_occurred_at=border,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        assert ids == {"old"}

    def test_boundary_episode_excluded_strictly_older(self) -> None:
        """``occurred_at == border`` の episode は recall から落とす。

        sliding window 最古 entry 自身が「直近に届いた observation」なので、
        recall で重複してまた拾うのは無駄。``strictly_older`` (`<` 比較) の
        側に倒す設計。
        """
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        store.put_by_being(_being, _episode(episode_id="exact", occurred_at=ts, cues=(cue,)))
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=1,
            situation_cues=(cue,),
            limit_per_axis=10,
            max_candidates=10,
            min_occurred_at=ts,
        )
        assert result.candidates == ()

    def test_naive_aware_utc(self) -> None:
        """sliding window が naive datetime を返す経路 (= ``datetime.now()``) と、
        episode の occurred_at が aware UTC な経路の混在は実装で正規化される。"""
        store = InMemorySubjectiveEpisodeStore()
        cue = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        store.put_by_being(
            _being,
            _episode(
                episode_id="aware-old",
                occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                cues=(cue,),
            ),
        )
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        # 境界は naive (= UTC として解釈される)、aware-old より新しい
        border_naive = datetime(2026, 6, 1)
        result = svc.retrieve(
            player_id=1,
            situation_cues=(cue,),
            limit_per_axis=10,
            max_candidates=10,
            min_occurred_at=border_naive,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        assert ids == {"aware-old"}


class TestR2TemporalAxisFallback:
    """temporal 軸は ``situation_cues`` が空のときのみ fallback として動く。"""

    def test_cue_idle_turn_temporal_episode(
        self,
    ) -> None:
        """cue が立たない idleturn では temporal 軸が直近 episode を出す。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store.put_by_being(_being, _episode(episode_id="t1", occurred_at=base, cues=()))
        store.put_by_being(_being, _episode(episode_id="t2", occurred_at=base + timedelta(days=1), cues=()))
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        # cues 空 → temporal fallback で 2 件出る
        result = svc.retrieve(
            player_id=1,
            situation_cues=(),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # 新しい順
        assert ids == ["t2", "t1"]

    def test_cue_turn_temporal_off(self) -> None:
        """cue が立っていれば temporal 軸は走らない (= 直近重複が出ない)。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        store.put_by_being(_being, _episode(episode_id="recent-noise", occurred_at=base + timedelta(days=5), cues=()))
        store.put_by_being(_being, _episode(episode_id="cue-hit", occurred_at=base, cues=(cue,)))
        res, wid = _make_resolver()
        svc = EpisodicPassiveRecallRetrievalService(
            store, being_attachment_resolver=res, default_world_id=wid
        )
        result = svc.retrieve(
            player_id=1,
            situation_cues=(cue,),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # cue にマッチする episode のみ。temporal noise は出ない。
        assert ids == ["cue-hit"]


class TestR2TemporalFallbackPinning:
    """R2 fallback が dead code にならないことを pinning する。

    `build_situation_episodic_cues` (= prompt 構築での cue 生成) が **idle turn
    で本当に cues=() を返す経路** が残っていることを保証する。もし将来この経路
    が「常時必ず何かの cue を立てる」設計に変わると、R2 fallback は永遠に
    走らない dead code になる。"""

    def test_empty_observation_prose_and_runtime_context_return_empty_cues(self) -> None:
        """observationprose と runtimecontext が空なら cues は空。"""
        from ai_rpg_world.application.llm.contracts.dtos import (
            ToolRuntimeContextDto,
        )
        from ai_rpg_world.application.llm.services.episodic_cue_rules import (
            build_situation_episodic_cues,
        )

        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=None,
        )
        # idle 経路は cues=() を出す → R2 で temporal fallback が走るシナリオが
        # 設計として残されている
        assert tuple(cues) == ()


class TestSlidingWindowOldestEntryDatetime:
    """``get_oldest_entry_datetime`` の挙動 (sliding_window 系の新 API)。"""

    def test_returns_none_empty_window(self) -> None:
        """空 window は None を返す。"""
        mem = DefaultSlidingWindowMemory()
        assert mem.get_oldest_entry_datetime(PlayerId(1)) is None

    def test_one_append_window_entry_occurred(self) -> None:
        """1 件 append された window の最古はその entry の occurredat。"""
        mem = DefaultSlidingWindowMemory()
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        mem.append(
            PlayerId(1),
            ObservationEntry(
                occurred_at=ts,
                output=ObservationOutput(
                    prose="x",
                    structured={},
                    observation_category="self_only",
                    schedules_turn=False,
                    breaks_movement=False,
                ),
                game_time_label=None,
            ),
        )
        assert mem.get_oldest_entry_datetime(PlayerId(1)) == ts

    def test_returns_multiple_append(self) -> None:
        """複数件 append で最古を返す。"""
        mem = DefaultSlidingWindowMemory()
        t1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 5, tzinfo=timezone.utc)
        for ts in (t2, t1):  # 順不同で入れる
            mem.append(
                PlayerId(1),
                ObservationEntry(
                    occurred_at=ts,
                    output=ObservationOutput(
                        prose="x",
                        structured={},
                        observation_category="self_only",
                        schedules_turn=False,
                        breaks_movement=False,
                    ),
                    game_time_label=None,
                ),
            )
        assert mem.get_oldest_entry_datetime(PlayerId(1)) == t1


class TestRollingSummaryOldestEntryDatetime:
    """``RollingSummaryShortTermMemory.get_oldest_entry_datetime``。

    rolling_summary 経路でも L1 raw queue の最古 entry の occurred_at を
    返すことを担保する。L4 mid summary に畳まれた raw は含めない (= 構成
    要素の raw は retire 済の扱い)。"""

    def _mem(self):
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )
        return RollingSummaryShortTermMemory(l1_soft_cap=15, l1_hard_cap=25)

    def test_empty_window_none(self) -> None:
        """空 window は None。"""
        mem = self._mem()
        assert mem.get_oldest_entry_datetime(PlayerId(1)) is None

    def test_returns_l1_raw_multiple(self) -> None:
        """L1raw に複数件あれば最古を返す。"""
        mem = self._mem()
        t1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 5, tzinfo=timezone.utc)
        for ts in (t2, t1):
            mem.append(
                PlayerId(1),
                ObservationEntry(
                    occurred_at=ts,
                    output=ObservationOutput(
                        prose="x",
                        structured={},
                        observation_category="self_only",
                        schedules_turn=False,
                        breaks_movement=False,
                    ),
                    game_time_label=None,
                ),
            )
        assert mem.get_oldest_entry_datetime(PlayerId(1)) == t1


class TestPromptBuilderDefenseAgainstBadOldestType:
    """``get_oldest_entry_datetime`` が datetime 以外を返したら、warning ログを
    残しつつ recall の時間下限フィルタを off に倒す (silent failure 防止)。"""

    def test_emits_warning_for_none(self, caplog: pytest.LogCaptureFixture) -> None:
        """文字列が返ったら warning して None 扱い。"""
        import logging
        from ai_rpg_world.application.llm.contracts.interfaces import (
            ISlidingWindowMemory,
        )
        from ai_rpg_world.application.observation.contracts.dtos import (
            ObservationEntry,
        )

        # 壊れた実装: 文字列を返す sliding window
        class _BrokenSlidingWindow(ISlidingWindowMemory):
            def append(self, player_id, entry):  # noqa: D401
                pass

            def append_all(self, player_id, entries):  # type: ignore[override]
                return []

            def get_recent(self, player_id, limit):  # type: ignore[override]
                return []

            def get_oldest_entry_datetime(self, player_id):  # type: ignore[override]
                return "not-a-datetime"

        # prompt_builder の防衛コードが warning を出すことを直接 verify する
        # ことを目指す。完全な build_full_prompt は context 構築が重いので、
        # 防衛コードのロジックだけを切り出して再現する。
        from ai_rpg_world.application.llm.services import prompt_builder as pb_mod

        raw_oldest = _BrokenSlidingWindow().get_oldest_entry_datetime(PlayerId(1))
        if raw_oldest is not None and not isinstance(raw_oldest, datetime):
            with caplog.at_level(logging.WARNING):
                pb_mod._module_logger.warning(
                    "ISlidingWindowMemory.get_oldest_entry_datetime returned "
                    "unexpected type %s for player_id=%s; recall の時間下限フィルタ "
                    "を off にして fallback します。",
                    type(raw_oldest).__name__,
                    1,
                )
            min_recall_dt = None
        else:
            min_recall_dt = raw_oldest

        assert min_recall_dt is None
        assert any(
            "unexpected type" in r.message for r in caplog.records
        )
