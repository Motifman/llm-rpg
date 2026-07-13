"""InMemoryPendingPredictionStore の per-Being 挙動 (容量上限 evict 含む) を

保証する。U10a (予測誤差統一設計 部品6・pending prediction)。
"""

from __future__ import annotations

import threading

from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PENDING_PREDICTION_DEFAULT_CAP,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)


def _pending(pending_id: str, created_tick: int) -> PendingPrediction:
    return PendingPrediction(
        pending_id=pending_id,
        text="約束",
        resolution_cues=("spot:1",),
        tick_from=created_tick,
        tick_to=created_tick + 5,
        origin_episode_id="ep-1",
        created_tick=created_tick,
    )


class TestInMemoryPendingPredictionStore:
    def test_add_and_list_all_by_being(self) -> None:
        store = InMemoryPendingPredictionStore()
        being_id = BeingId("being-1")
        store.add_by_being(being_id, _pending("p1", 1))
        store.add_by_being(being_id, _pending("p2", 2))

        rows = store.list_all_by_being(being_id)
        assert [p.pending_id for p in rows] == ["p1", "p2"]

    def test_add_by_being_returns_none_when_capacity_not_exceeded(self) -> None:
        """容量に余裕があるうちの追加は evict が起きないので None を返す。"""
        store = InMemoryPendingPredictionStore(capacity=3)
        being_id = BeingId("being-1")
        assert store.add_by_being(being_id, _pending("p1", 1)) is None
        assert store.add_by_being(being_id, _pending("p2", 2)) is None

    def test_default_capacity_matches_repository_constant(self) -> None:
        assert PENDING_PREDICTION_DEFAULT_CAP == 8

    def test_capacity_overflow_evicts_oldest_by_created_tick(self) -> None:
        """容量上限を超えたら created_tick が最小のものから evict される。"""
        store = InMemoryPendingPredictionStore(capacity=3)
        being_id = BeingId("being-1")
        for i, tick in enumerate([5, 1, 3]):
            store.add_by_being(being_id, _pending(f"p{i}", tick))
        # ticks: p0=5, p1=1, p2=3 (すべて容量内)
        assert {p.pending_id for p in store.list_all_by_being(being_id)} == {
            "p0",
            "p1",
            "p2",
        }
        # 4件目追加で最古 (p1, tick=1) が evict される
        evicted = store.add_by_being(being_id, _pending("p3", 10))
        remaining = {p.pending_id for p in store.list_all_by_being(being_id)}
        assert remaining == {"p0", "p2", "p3"}
        assert "p1" not in remaining
        # evict された PendingPrediction 自体が戻り値として返る (呼び出し側が
        # trace を残せるようにするため)。
        assert evicted is not None
        assert evicted.pending_id == "p1"

    def test_capacity_overflow_keeps_bucket_size_bounded(self) -> None:
        store = InMemoryPendingPredictionStore(capacity=3)
        being_id = BeingId("being-1")
        for i in range(10):
            store.add_by_being(being_id, _pending(f"p{i}", i))
        assert len(store.list_all_by_being(being_id)) == 3

    def test_different_beings_are_isolated(self) -> None:
        store = InMemoryPendingPredictionStore()
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")
        store.add_by_being(being_a, _pending("pa", 1))
        assert store.list_all_by_being(being_a)
        assert store.list_all_by_being(being_b) == []

    def test_replace_all_by_being_overwrites(self) -> None:
        store = InMemoryPendingPredictionStore()
        being_id = BeingId("being-1")
        store.add_by_being(being_id, _pending("p1", 1))
        store.replace_all_by_being(being_id, [_pending("p2", 2), _pending("p3", 3)])
        rows = store.list_all_by_being(being_id)
        assert [p.pending_id for p in rows] == ["p2", "p3"]

    def test_replace_all_by_being_empty_clears(self) -> None:
        store = InMemoryPendingPredictionStore()
        being_id = BeingId("being-1")
        store.add_by_being(being_id, _pending("p1", 1))
        store.replace_all_by_being(being_id, [])
        assert store.list_all_by_being(being_id) == []


class TestInMemoryPendingPredictionStoreThreadSafety:
    """横断レビュー H-3/M2: ThreadPool ワーカーとメイン thread の同時アクセス。"""

    def test_lock_is_reentrant_so_all_public_methods_work_while_held(self) -> None:
        """外側で ``_lock`` を保持したまま全公開メソッドを呼んでもデッドロックしない
        (RLock による再入可能性の確認)。"""
        store = InMemoryPendingPredictionStore()
        being_id = BeingId("being-1")
        with store._lock:
            store.add_by_being(being_id, _pending("p1", 1))
            store.list_all_by_being(being_id)
            store.replace_all_by_being(being_id, [_pending("p1", 1)])

    def test_concurrent_add_and_list_yields_consistent_snapshots(self) -> None:
        """ワーカー thread の ``add_by_being`` と、メイン thread の
        ``list_all_by_being`` を並走させても、(1) 例外や部分書き込みの観測が
        起きず、(2) どの snapshot にも重複が無く、(3) 並走終了後に add した
        全件が揃っていることを保証する (= メソッド単位の RLock が実際に
        保証する性質のみを主張する)。

        注意: 「add と『list→replace の複合操作』の並走で無損失」はこの
        ロックでは保証されない (list と replace の間の窓は守れない)。本番で
        清算 (``resolve_pending_predictions_if_applicable`` の list→replace)
        と記録 (add) が安全なのは、ThreadPoolEpisodicSubjectiveScheduler の
        既定 max_workers=1 により同一 worker thread で直列に走るためであり、
        本テストの対象外 (``_pending_prediction_resolution.py`` の制約
        コメント参照)。容量上限に達しないよう capacity は件数より大きく取る
        (evict との混同を避ける)。
        """
        total = 300
        store = InMemoryPendingPredictionStore(capacity=total * 2)
        being_id = BeingId("being-stress")
        snapshot_errors: list[str] = []

        def adder() -> None:
            for i in range(total):
                store.add_by_being(being_id, _pending(f"p{i}", i))

        def reader() -> None:
            for _ in range(total):
                snapshot = store.list_all_by_being(being_id)
                ids = [p.pending_id for p in snapshot]
                if len(ids) != len(set(ids)):
                    snapshot_errors.append(f"duplicate ids in snapshot: {ids}")
                    return
                if not all(isinstance(p, PendingPrediction) for p in snapshot):
                    snapshot_errors.append("non-PendingPrediction in snapshot")
                    return

        t_add = threading.Thread(target=adder)
        t_read = threading.Thread(target=reader)
        t_add.start()
        t_read.start()
        t_add.join(timeout=10)
        t_read.join(timeout=10)
        assert not t_add.is_alive()
        assert not t_read.is_alive()
        assert snapshot_errors == []

        rows = store.list_all_by_being(being_id)
        assert len(rows) == total
        assert {p.pending_id for p in rows} == {f"p{i}" for i in range(total)}
