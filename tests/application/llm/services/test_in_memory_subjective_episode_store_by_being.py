"""``InMemorySubjectiveEpisodeStore`` の being_id 版 API テスト
(Phase 3 Step 3e-1)。

並走追加された 4 ``*_by_being`` メソッドが legacy player_id 版と互いに
見えないことと、各メソッドの基本挙動を確認する。memo / semantic /
memory_link / recall_buffer と同じパターン。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
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


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _episode(
    *,
    episode_id: str,
    player_id: int = 1,
    occurred_at: datetime = _NOW,
    cues: tuple[EpisodicCue, ...] = (),
) -> SubjectiveEpisode:
    if not cues:
        cues = (
            EpisodicCue(
                axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
            ),
        )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("e1",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted="i",
        cues=cues,
        recall_text="r",
        recall_count=0,
        last_recalled_at=None,
    )


@pytest.fixture
def store() -> InMemorySubjectiveEpisodeStore:
    return InMemorySubjectiveEpisodeStore()


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestPutAndGetByBeing:
    """put_by_being / get_by_being の基本挙動。"""

    def test_new_put_get_can_get(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """新規 put は get で取得できる。"""
        ep = _episode(episode_id="e1")
        store.put_by_being(being, ep)
        got = store.get_by_being(being, "e1")
        assert got is not None
        assert got.episode_id == "e1"

    def test_same_episode_id_put(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """同一 episodeid の put は上書き。"""
        store.put_by_being(being, _episode(episode_id="e1"))
        store.put_by_being(
            being, _episode(episode_id="e1", occurred_at=_NOW + timedelta(hours=1))
        )
        got = store.get_by_being(being, "e1")
        assert got is not None
        assert got.occurred_at == _NOW + timedelta(hours=1)

    def test_being_id_raises_type_error(
        self, store: InMemorySubjectiveEpisodeStore
    ) -> None:
        """being id 型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            store.put_by_being("not-a-being", _episode(episode_id="e1"))  # type: ignore[arg-type]


class TestListRecentByBeing:
    """list_recent_by_being の挙動。"""

    def test_returns_occurred(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """occurredat 降順で返る。"""
        store.put_by_being(being, _episode(episode_id="old", occurred_at=_NOW - timedelta(hours=1)))
        store.put_by_being(being, _episode(episode_id="new", occurred_at=_NOW))
        result = store.list_recent_by_being(being, limit=10)
        assert [ep.episode_id for ep in result] == ["new", "old"]

    def test_limit_zero_less_empty_list(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """limit 0 以下は 空 list。"""
        store.put_by_being(being, _episode(episode_id="e1"))
        assert store.list_recent_by_being(being, limit=0) == []


class TestListByCueByBeing:
    """list_by_cue_by_being の挙動。"""

    def test_returns_cue_matches_episode(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """cue に一致する episode を返す。"""
        cue_a = EpisodicCue(
            axis="entity", value="alice", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        cue_b = EpisodicCue(
            axis="entity", value="bob", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        store.put_by_being(being, _episode(episode_id="ea", cues=(cue_a,)))
        store.put_by_being(being, _episode(episode_id="eb", cues=(cue_b,)))
        result = store.list_by_cue_by_being(being, cue_a, limit=10)
        assert [ep.episode_id for ep in result] == ["ea"]

    def test_cue_index_put_updated(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """cueindex は put で更新される。"""
        cue_old = EpisodicCue(
            axis="entity", value="old", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        cue_new = EpisodicCue(
            axis="entity", value="new", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        store.put_by_being(being, _episode(episode_id="e1", cues=(cue_old,)))
        store.put_by_being(being, _episode(episode_id="e1", cues=(cue_new,)))
        # old cue では見えない
        assert store.list_by_cue_by_being(being, cue_old, limit=10) == []
        # new cue で見える
        assert len(store.list_by_cue_by_being(being, cue_new, limit=10)) == 1


# Phase 3 Step 3e-3 (Issue #470): legacy player_id 版 API 撤去に伴い
# ``TestIndependenceFromPlayerIdApi`` は削除済 (= 並走パスが無くなり
# 独立性の概念自体が消えた)。新 API only に統一。


class TestEvictionByBeing:
    """``max_episodes_per_player`` 上限が being_id 版にも効く。"""

    def test_exceeds_evict(
        self, being: BeingId
    ) -> None:
        """上限超過時は 最古から evict。"""
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=2)
        store.put_by_being(
            being,
            _episode(episode_id="oldest", occurred_at=_NOW - timedelta(hours=2)),
        )
        store.put_by_being(
            being,
            _episode(episode_id="mid", occurred_at=_NOW - timedelta(hours=1)),
        )
        store.put_by_being(being, _episode(episode_id="newest", occurred_at=_NOW))
        # 上限 2 件 → oldest が evict される
        result = store.list_recent_by_being(being, limit=10)
        assert [ep.episode_id for ep in result] == ["newest", "mid"]


class TestEpisodeReplaceAll:
    """Phase 4 Step 4-2a: list_all_by_being / replace_all_by_being。"""

    def test_list_all_occurred(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """list all は occurred at 昇順。"""
        from datetime import datetime, timezone
        e1 = _episode(
            episode_id="e1",
            occurred_at=datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
        )
        e2 = _episode(
            episode_id="e2",
            occurred_at=datetime(2026, 6, 14, 11, 0, tzinfo=timezone.utc),
        )
        store.put_by_being(being, e1)
        store.put_by_being(being, e2)
        ids = [e.episode_id for e in store.list_all_by_being(being)]
        assert ids == ["e2", "e1"]

    def test_replace_all_cue_index(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """replace all で全置換とcue index再構築。"""
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import (
            EpisodicCue,
        )
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
            EpisodicCueSource,
        )

        old = _episode(episode_id="old")
        store.put_by_being(being, old)
        cue_new = EpisodicCue(
            axis="place_spot", value="999", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        new = _episode(episode_id="new", cues=(cue_new,))
        store.replace_all_by_being(being, [new])
        assert [e.episode_id for e in store.list_all_by_being(being)] == ["new"]
        # cue index: 新 cue で hit、旧 cue では空。
        hit = store.list_by_cue_by_being(being, cue_new, limit=10)
        assert [e.episode_id for e in hit] == ["new"]

    def test_other_being_does_not_affect(
        self, store: InMemorySubjectiveEpisodeStore
    ) -> None:
        """他 being は影響しない。"""
        a = BeingId("being_w1_p1")
        b = BeingId("being_w1_p2")
        store.put_by_being(a, _episode(episode_id="a"))
        store.put_by_being(b, _episode(episode_id="b"))
        store.replace_all_by_being(a, [])
        assert [e.episode_id for e in store.list_all_by_being(b)] == ["b"]
