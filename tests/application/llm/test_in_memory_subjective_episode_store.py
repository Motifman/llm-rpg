"""InMemorySubjectiveEpisodeStore の契約テスト。"""

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def _episode(
    *,
    episode_id: str = "ep-1",
    player_id: int = 7,
    occurred_at: datetime | None = None,
    cues: tuple[EpisodicCue, ...] | None = None,
    recall_text: str = "r",
) -> SubjectiveEpisode:
    ts = occurred_at or datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
    cue_list = cues or (
        EpisodicCue(axis="place_spot", value="12", source=EpisodicCueSource.RUNTIME_CONTEXT),
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=ts,
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
        intended_next=None,
        cues=cue_list,
        recall_text=recall_text,
    )


class TestInMemorySubjectiveEpisodeStoreBasics:
    """保存・取得・空結果"""

    def test_put_and_get_returns_same_episode(self) -> None:
        """put した SubjectiveEpisode が get で同一内容として読み戻せる。"""
        store = InMemorySubjectiveEpisodeStore()
        ep = _episode()
        store.put(ep)
        got = store.get(7, "ep-1")
        assert got is ep

    def test_get_missing_returns_none(self) -> None:
        """未保存の episode_id は None。"""
        store = InMemorySubjectiveEpisodeStore()
        assert store.get(7, "missing") is None

    def test_list_recent_non_positive_limit_empty(self) -> None:
        """limit が 0 以下なら recent は空。"""
        store = InMemorySubjectiveEpisodeStore()
        store.put(_episode())
        assert store.list_recent(7, 0) == []
        assert store.list_recent(7, -1) == []

    def test_list_recent_sorts_naive_and_aware_occurred_at_without_error(self) -> None:
        """naive と aware の occurred_at が混在してもソートで TypeError にしない（naive は UTC 相当）。"""
        store = InMemorySubjectiveEpisodeStore()
        naive_later = _episode(
            episode_id="naive",
            occurred_at=datetime(2026, 5, 4, 12, 0),
        )
        aware_earlier = _episode(
            episode_id="aware",
            occurred_at=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        )
        store.put(aware_earlier)
        store.put(naive_later)
        ordered = store.list_recent(7, 10)
        assert [e.episode_id for e in ordered] == ["naive", "aware"]


class TestInMemorySubjectiveEpisodeStorePlayerScope:
    """player_id でデータが混線しないこと"""

    def test_same_episode_id_different_players_isolated(self) -> None:
        """同一 episode_id でも player が違えば別レコードとして保持する。"""
        store = InMemorySubjectiveEpisodeStore()
        a = _episode(episode_id="shared-id", player_id=1, recall_text="p1")
        b = _episode(episode_id="shared-id", player_id=2, recall_text="p2")
        store.put(a)
        store.put(b)
        assert store.get(1, "shared-id") is a
        assert store.get(2, "shared-id") is b

    def test_list_recent_only_same_player(self) -> None:
        """list_recent は対象プレイヤーのエピソードのみ返す。"""
        store = InMemorySubjectiveEpisodeStore()
        store.put(_episode(episode_id="e1", player_id=10))
        store.put(_episode(episode_id="e2", player_id=20))
        assert len(store.list_recent(10, 10)) == 1
        assert store.list_recent(10, 10)[0].episode_id == "e1"


class TestInMemorySubjectiveEpisodeStoreRecentOrder:
    """occurred_at 降順・タイブレーク"""

    def test_list_recent_orders_by_occurred_at_desc(self) -> None:
        """より新しい occurred_at が先頭になる。"""
        store = InMemorySubjectiveEpisodeStore()
        older = _episode(
            episode_id="old",
            occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        newer = _episode(
            episode_id="new",
            occurred_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )
        store.put(older)
        store.put(newer)
        recent = store.list_recent(7, 10)
        assert [e.episode_id for e in recent] == ["new", "old"]

    def test_list_recent_tie_breaker_episode_id_desc(self) -> None:
        """occurred_at が同一なら episode_id 降順で安定ソートする。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 5, 3, tzinfo=timezone.utc)
        store.put(_episode(episode_id="b", occurred_at=ts))
        store.put(_episode(episode_id="a", occurred_at=ts))
        recent = store.list_recent(7, 10)
        assert [e.episode_id for e in recent] == ["b", "a"]


class TestInMemorySubjectiveEpisodeStoreCueIndex:
    """cue 逆引き（canonical）"""

    def test_list_by_cue_matches_canonical_not_source(self) -> None:
        """索引キーは cue.to_canonical() のみ。source が異なっても同じ軸値ならヒットする。"""
        store = InMemorySubjectiveEpisodeStore()
        store.put(
            _episode(
                episode_id="with-runtime",
                cues=(
                    EpisodicCue(
                        axis="action",
                        value="open",
                        source=EpisodicCueSource.RUNTIME_CONTEXT,
                    ),
                ),
            )
        )
        query = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        found = store.list_by_cue(7, query, 10)
        assert len(found) == 1
        assert found[0].episode_id == "with-runtime"

    def test_list_by_cue_respects_player_scope(self) -> None:
        """他プレイヤーの cue 索引は見えない。"""
        store = InMemorySubjectiveEpisodeStore()
        c = (
            EpisodicCue(axis="x", value="1", source=EpisodicCueSource.TOOL),
        )
        store.put(_episode(episode_id="p10", player_id=10, cues=c))
        q = EpisodicCue(axis="x", value="1", source=EpisodicCueSource.TOOL)
        assert store.list_by_cue(99, q, 10) == []

    def test_list_by_cue_non_positive_limit_empty(self) -> None:
        """list_by_cue も limit が 0 以下なら空リスト。"""
        store = InMemorySubjectiveEpisodeStore()
        cue = EpisodicCue(axis="z", value="9", source=EpisodicCueSource.TOOL)
        store.put(_episode(cues=(cue,)))
        assert store.list_by_cue(7, cue, 0) == []

    def test_list_by_cue_sorted_like_recent(self) -> None:
        """list_by_cue も occurred_at 降順・同一時刻は episode_id 降順。"""
        store = InMemorySubjectiveEpisodeStore()
        cue = EpisodicCue(axis="place_spot", value="9", source=EpisodicCueSource.TOOL)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put(_episode(episode_id="b", occurred_at=ts, cues=(cue,)))
        store.put(
            _episode(
                episode_id="a",
                occurred_at=ts,
                cues=(cue,),
            )
        )
        store.put(
            _episode(
                episode_id="later",
                occurred_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                cues=(cue,),
            )
        )
        got = store.list_by_cue(7, cue, 10)
        assert [e.episode_id for e in got] == ["later", "b", "a"]


class TestInMemorySubjectiveEpisodeStoreUpsert:
    """同一 episode_id を put したときの索引・本体の更新"""

    def test_put_same_episode_id_replaces_and_updates_cue_index(self) -> None:
        """
        同一 (player_id, episode_id) で再 put すると upsert。
        旧 cue のみに載っていた索引からは外れ、新 cue で逆引きできる。
        """
        store = InMemorySubjectiveEpisodeStore()
        old_cue = EpisodicCue(axis="old", value="1", source=EpisodicCueSource.TOOL)
        new_cue = EpisodicCue(axis="new", value="2", source=EpisodicCueSource.TOOL)
        store.put(_episode(episode_id="same", cues=(old_cue,), recall_text="v1"))
        store.put(_episode(episode_id="same", cues=(new_cue,), recall_text="v2"))

        latest = store.get(7, "same")
        assert latest is not None
        assert latest.recall_text == "v2"

        assert store.list_by_cue(7, old_cue, 10) == []
        assert len(store.list_by_cue(7, new_cue, 10)) == 1
