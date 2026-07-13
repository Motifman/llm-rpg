"""``InMemoryEpisodicRecallBufferStore`` / ``InMemoryEpisodicReinterpretationJournalStore``
の being_id 版 API テスト (Phase 3 Step 3d-1)。

並走追加された ``*_by_being`` メソッド群が legacy player_id 版と互いに見え
ないことと、各メソッドが期待通り動くことを確認する。memo / semantic /
memory_link と同じパターン。
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _obs(
    *,
    recall_id: str,
    episode_id: str,
    player_id: int = 1,
    recalled_at: datetime = _NOW,
    prediction_context_id: str | None = None,
    prediction_outcome_error: str | None = None,
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=player_id,
        episode_id=episode_id,
        recalled_at=recalled_at,
        source_axes=("temporal",),
        current_state_snapshot="state",
        recent_events_snapshot="events",
        persona_snapshot="persona",
        situation_cues=("cue",),
        turn_index=1,
        prediction_context_id=prediction_context_id,
        prediction_outcome_error=prediction_outcome_error,
    )


def _entry(
    *,
    entry_id: str,
    episode_id: str,
    player_id: int = 1,
    created_at: datetime = _NOW,
    status: EpisodicReinterpretationStatus = EpisodicReinterpretationStatus.ACTIVE,
) -> EpisodicReinterpretationEntry:
    return EpisodicReinterpretationEntry(
        entry_id=entry_id,
        player_id=player_id,
        episode_id=episode_id,
        created_at=created_at,
        turn_index=1,
        current_interpretation="reinterp",
        current_recall_text="recall",
        source_recall_ids=("r-1",),
        status=status,
        superseded_at=None,
    )


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestRecallBufferByBeing:
    """``InMemoryEpisodicRecallBufferStore`` の by_being API。"""

    def test_append_と_pending_count(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        assert store.pending_count_by_being(being) == 2

    def test_peek_batch_は_episode_batched_順序を保つ(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being, _obs(recall_id="r1", episode_id="e1", recalled_at=_NOW)
        )
        store.append_by_being(
            being,
            _obs(
                recall_id="r2",
                episode_id="e2",
                recalled_at=_NOW + timedelta(seconds=1),
            ),
        )
        result = store.peek_batch_by_being(
            being, batch_size=2, max_contexts_per_episode=5
        )
        assert len(result) == 2
        assert result[0].recall_id == "r1"
        assert result[1].recall_id == "r2"

    def test_peek_batch_は_batch_size_を_守る(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        for i in range(5):
            store.append_by_being(
                being,
                _obs(
                    recall_id=f"r{i}",
                    episode_id=f"e{i}",
                    recalled_at=_NOW + timedelta(seconds=i),
                ),
            )
        result = store.peek_batch_by_being(
            being, batch_size=2, max_contexts_per_episode=5
        )
        episodes = {r.episode_id for r in result}
        assert len(episodes) == 2

    def test_mark_processed_は_pending_から_除く(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        store.mark_processed_by_being(being, ("r1",))
        assert store.pending_count_by_being(being) == 1

    def test_型違反は_TypeError(self) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        with pytest.raises(TypeError, match="being_id"):
            store.append_by_being("not-being", _obs(recall_id="r", episode_id="e"))  # type: ignore[arg-type]

    def test_batch_size_0_は_空_tuple(self, being: BeingId) -> None:
        """``batch_size <= 0`` は早期 return で空 tuple (= disabled 経路)。"""
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=0, max_contexts_per_episode=5
            )
            == ()
        )

    def test_max_contexts_per_episode_0_は_空_tuple(self, being: BeingId) -> None:
        """``max_contexts_per_episode <= 0`` も早期 return で空 tuple。"""
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=5, max_contexts_per_episode=0
            )
            == ()
        )


# Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API が撤去されたため、
# 旧/新 API の独立性を検証していたテストクラス ``TestRecallBufferIsolation``
# は削除された。新 API のみが残り、being_id を一次キーとして扱う設計に統一。


class TestRecallBufferStampPredictionOutcome:
    """U9a: ``stamp_prediction_outcome_by_being`` の挙動。"""

    def test_一致する_prediction_context_id_の未処理_obs_に誤差が載る(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "外れた: 実際は雨だった")
        got = store.list_pending_by_being(being)[0]
        assert got.prediction_outcome_error == "外れた: 実際は雨だった"

    def test_別の_prediction_context_id_の_obs_には載らない(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", prediction_context_id="pc-2"),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "外れた")
        rows = {o.recall_id: o for o in store.list_pending_by_being(being)}
        assert rows["r1"].prediction_outcome_error == "外れた"
        assert rows["r2"].prediction_outcome_error is None

    def test_既に誤差が刻まれた_obs_は上書きしない(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(
                recall_id="r1",
                episode_id="e1",
                prediction_context_id="pc-1",
                prediction_outcome_error="最初の誤差",
            ),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "二度目の誤差")
        got = store.list_pending_by_being(being)[0]
        assert got.prediction_outcome_error == "最初の誤差"

    def test_一致するものが無ければ何もしない(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-nonexistent", "誤差")
        got = store.list_pending_by_being(being)[0]
        assert got.prediction_outcome_error is None

    def test_型違反は_TypeError(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        with pytest.raises(TypeError, match="being_id"):
            store.stamp_prediction_outcome_by_being("not-being", "pc-1", "誤差")  # type: ignore[arg-type]


class TestRecallBufferListEpisodeIdsByPredictionContext:
    """U9b: ``list_episode_ids_by_prediction_context_by_being`` の挙動。

    外れ側 (``stamp_prediction_outcome_by_being``) の読み出し版で、的中側
    (recall success store への record_hit) がどの episode を想起して立てた
    予測だったかを特定するために使う。
    """

    def test_一致する_prediction_context_id_の_episode_id_を返す(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert got == ("e1",)

    def test_複数_episode_が_同じ_prediction_context_id_に紐づく場合は全件返す(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert set(got) == {"e1", "e2"}

    def test_同じ_episode_を複数_recall_しても重複排除される(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert got == ("e1",)

    def test_別の_prediction_context_id_の_episode_は含まれない(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", prediction_context_id="pc-2"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert got == ("e1",)

    def test_一致するものが無ければ空tuple(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(
            being, "pc-nonexistent"
        )
        assert got == ()

    def test_型違反は_TypeError(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        with pytest.raises(TypeError, match="being_id"):
            store.list_episode_ids_by_prediction_context_by_being(
                "not-being", "pc-1"  # type: ignore[arg-type]
            )

    def test_prediction_context_id_が空文字なら_ValueError(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        with pytest.raises(ValueError):
            store.list_episode_ids_by_prediction_context_by_being(being, "")


class TestJournalByBeing:
    """``InMemoryEpisodicReinterpretationJournalStore`` の by_being API。"""

    def test_put_active_と_get_active(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        e1 = _entry(entry_id="ent-1", episode_id="ep-1")
        store.put_active_by_being(being, e1)
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None
        assert got.entry_id == "ent-1"

    def test_新しい_active_を_保存すると_旧_active_は_superseded(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        e1 = _entry(entry_id="old", episode_id="ep-1")
        e2 = _entry(
            entry_id="new",
            episode_id="ep-1",
            created_at=_NOW + timedelta(minutes=1),
        )
        store.put_active_by_being(being, e1)
        store.put_active_by_being(being, e2)
        # 新しい active のみ get_active で返る
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None and got.entry_id == "new"
        # 履歴には 2 件
        hist = store.list_by_episode_by_being(being, "ep-1")
        assert len(hist) == 2
        # 1 件は SUPERSEDED
        assert any(
            e.status == EpisodicReinterpretationStatus.SUPERSEDED for e in hist
        )

    def test_put_active_に_非_ACTIVE_を_渡すと_ValueError(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        bad = _entry(
            entry_id="bad",
            episode_id="ep-1",
            status=EpisodicReinterpretationStatus.SUPERSEDED,
        )
        with pytest.raises(ValueError, match="active"):
            store.put_active_by_being(being, bad)

    def test_型違反は_TypeError(self) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        with pytest.raises(TypeError, match="being_id"):
            store.put_active_by_being(
                "not-being",  # type: ignore[arg-type]
                _entry(entry_id="x", episode_id="ep"),
            )


# Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API 撤去に伴い
# ``TestJournalIsolation`` も削除済。新 API only に統一。


class TestRecallBufferReplaceAll:
    """Phase 4 Step 4-2a: list_pending_by_being / replace_all_pending_by_being。"""

    def test_list_pending_は全件_古い順(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        ids = [o.recall_id for o in store.list_pending_by_being(being)]
        assert ids == ["r1", "r2"]

    def test_replace_all_pending_で一括置換(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="old", episode_id="e1"))
        store.replace_all_pending_by_being(
            being, [_obs(recall_id="new", episode_id="e2")]
        )
        ids = [o.recall_id for o in store.list_pending_by_being(being)]
        assert ids == ["new"]

    def test_空リストで全クリア(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.replace_all_pending_by_being(being, [])
        assert store.pending_count_by_being(being) == 0


class TestRecallBufferThreadSafety:
    """横断レビュー H-3/M2: ThreadPool ワーカーとメイン thread の同時アクセス。

    ``InMemoryEpisodicRecallBufferStore`` のみが対象 (``InMemoryEpisodicReinterpretationJournalStore``
    はワーカー thread から呼ばれる経路が無いため対象外)。
    """

    def test_lock_is_reentrant_so_all_public_methods_work_while_held(
        self, being: BeingId
    ) -> None:
        """外側で ``_lock`` を保持したまま全公開メソッドを呼んでもデッドロックしない
        (RLock による再入可能性の確認)。"""
        store = InMemoryEpisodicRecallBufferStore()
        with store._lock:
            store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
            store.pending_count_by_being(being)
            store.list_pending_by_being(being)
            store.peek_batch_by_being(being, batch_size=1, max_contexts_per_episode=1)
            store.stamp_prediction_outcome_by_being(being, "ctx-1", "誤差")
            store.list_episode_ids_by_prediction_context_by_being(being, "ctx-1")
            store.mark_processed_by_being(being, ("r1",))
            store.replace_all_pending_by_being(being, [])

    def test_concurrent_append_and_stamp_prediction_outcome_never_loses_observations(
        self, being: BeingId
    ) -> None:
        """ワーカー thread の ``append_by_being`` と、誤差駆動再解釈の完了点で
        呼ばれる ``stamp_prediction_outcome_by_being`` (list 読み取り →
        更新版差し替えの read-modify-write) を並走させても、append した
        recall observation が無音で消えない。

        stamp 側はマッチしない ``prediction_context_id`` を渡し、実質
        no-op のまま read-modify-write の競合窓だけを突く。
        """
        total = 300
        store = InMemoryEpisodicRecallBufferStore()
        being_id = being

        def appender() -> None:
            for i in range(total):
                store.append_by_being(
                    being_id,
                    _obs(recall_id=f"r{i}", episode_id=f"e{i}"),
                )

        def stamper() -> None:
            for _ in range(total):
                store.stamp_prediction_outcome_by_being(
                    being_id, "no-such-context", "誤差"
                )

        t_append = threading.Thread(target=appender)
        t_stamp = threading.Thread(target=stamper)
        t_append.start()
        t_stamp.start()
        t_append.join(timeout=10)
        t_stamp.join(timeout=10)
        assert not t_append.is_alive()
        assert not t_stamp.is_alive()

        rows = store.list_pending_by_being(being_id)
        assert len(rows) == total
        assert {o.recall_id for o in rows} == {f"r{i}" for i in range(total)}


class TestJournalReplaceAll:
    """Phase 4 Step 4-2a: list_all_by_being / replace_all_by_being。"""

    def test_list_all_by_being_は全episode横断(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        store.put_active_by_being(being, _entry(entry_id="a", episode_id="ep-1"))
        store.put_active_by_being(being, _entry(entry_id="b", episode_id="ep-2"))
        ids = [e.entry_id for e in store.list_all_by_being(being)]
        assert set(ids) == {"a", "b"}

    def test_replace_all_でactive_index_が再構築される(
        self, being: BeingId
    ) -> None:
        """ACTIVE entry を持ち込めば get_active_by_being で引ける。"""
        store = InMemoryEpisodicReinterpretationJournalStore()
        store.put_active_by_being(being, _entry(entry_id="a", episode_id="ep-1"))
        new = _entry(entry_id="new", episode_id="ep-1")
        store.replace_all_by_being(being, [new])
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None
        assert got.entry_id == "new"

    def test_replace_all_の空で_active_も消える(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        store.put_active_by_being(being, _entry(entry_id="a", episode_id="ep-1"))
        store.replace_all_by_being(being, [])
        assert store.get_active_by_being(being, "ep-1") is None
        assert store.list_all_by_being(being) == []
