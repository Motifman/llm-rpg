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

    def test_新規_put_は_get_で_取得できる(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        ep = _episode(episode_id="e1")
        store.put_by_being(being, ep)
        got = store.get_by_being(being, "e1")
        assert got is not None
        assert got.episode_id == "e1"

    def test_同一_episode_id_の_put_は_上書き(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put_by_being(being, _episode(episode_id="e1"))
        store.put_by_being(
            being, _episode(episode_id="e1", occurred_at=_NOW + timedelta(hours=1))
        )
        got = store.get_by_being(being, "e1")
        assert got is not None
        assert got.occurred_at == _NOW + timedelta(hours=1)

    def test_being_id_型違反は_TypeError(
        self, store: InMemorySubjectiveEpisodeStore
    ) -> None:
        with pytest.raises(TypeError, match="being_id"):
            store.put_by_being("not-a-being", _episode(episode_id="e1"))  # type: ignore[arg-type]


class TestListRecentByBeing:
    """list_recent_by_being の挙動。"""

    def test_occurred_at_降順_で_返る(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put_by_being(being, _episode(episode_id="old", occurred_at=_NOW - timedelta(hours=1)))
        store.put_by_being(being, _episode(episode_id="new", occurred_at=_NOW))
        result = store.list_recent_by_being(being, limit=10)
        assert [ep.episode_id for ep in result] == ["new", "old"]

    def test_limit_0_以下は_空_list(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put_by_being(being, _episode(episode_id="e1"))
        assert store.list_recent_by_being(being, limit=0) == []


class TestListByCueByBeing:
    """list_by_cue_by_being の挙動。"""

    def test_cue_に_一致する_episode_を_返す(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
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

    def test_cue_index_は_put_で_更新される(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
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


class TestIndependenceFromPlayerIdApi:
    """新旧 API の独立性 (= 並走 index は同期しない)。"""

    def test_player_id_経由で_put_した_episode_は_being_id_経由では_見えない(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put(_episode(episode_id="legacy", player_id=1))
        assert store.get_by_being(being, "legacy") is None
        assert store.list_recent_by_being(being, limit=10) == []

    def test_being_id_経由で_put_した_episode_は_player_id_経由では_見えない(
        self, store: InMemorySubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put_by_being(being, _episode(episode_id="new", player_id=1))
        assert store.get(1, "new") is None
        assert store.list_recent(1, limit=10) == []


class TestEvictionByBeing:
    """``max_episodes_per_player`` 上限が being_id 版にも効く。"""

    def test_上限超過時は_最古から_evict(
        self, being: BeingId
    ) -> None:
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
