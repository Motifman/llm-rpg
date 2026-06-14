"""InMemoryMemoStore の being_id 版 API 挙動 (Phase 3 Step 3a-1)。

旧 ``player_id`` 版とは独立した namespace で動くこと、CRUD・完了・並び順・
独立性 (= 旧 API との混在禁止) を担保する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)
@pytest.fixture
def store() -> InMemoryMemoStore:
    return InMemoryMemoStore()


class TestAddByBeing:
    """add_by_being の挙動。"""

    def test_有効な引数で_memo_を追加できる(self, store: InMemoryMemoStore) -> None:
        """正常系: 追加すると生成された ID が返り、list_uncompleted_by_being で取れる。"""
        memo_id = store.add_by_being(BeingId("ada"), "今夜は山小屋に泊まる")
        assert isinstance(memo_id, str) and memo_id
        entries = store.list_uncompleted_by_being(BeingId("ada"))
        assert len(entries) == 1
        assert entries[0].id == memo_id
        assert entries[0].content == "今夜は山小屋に泊まる"

    def test_current_tick_を渡すと_added_at_tick_に乗る(
        self, store: InMemoryMemoStore
    ) -> None:
        """current_tick の保存。"""
        store.add_by_being(BeingId("ada"), "test", current_tick=42)
        entries = store.list_uncompleted_by_being(BeingId("ada"))
        assert entries[0].added_at_tick == 42

    def test_being_id_が_VO_でないと_TypeError(
        self, store: InMemoryMemoStore
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="being_id"):
            store.add_by_being("ada", "test")  # type: ignore[arg-type]

    def test_content_が_str_でないと_TypeError(
        self, store: InMemoryMemoStore
    ) -> None:
        """content の型違反は TypeError。"""
        with pytest.raises(TypeError, match="content"):
            store.add_by_being(BeingId("ada"), 42)  # type: ignore[arg-type]

    def test_current_tick_が_int_でないと_TypeError(
        self, store: InMemoryMemoStore
    ) -> None:
        """current_tick の型違反は TypeError。"""
        with pytest.raises(TypeError, match="current_tick"):
            store.add_by_being(
                BeingId("ada"), "test", current_tick="42"  # type: ignore[arg-type]
            )


class TestListUncompletedByBeing:
    """list_uncompleted_by_being の挙動。"""

    def test_未追加の_being_には_空リスト(self, store: InMemoryMemoStore) -> None:
        """未登録 being_id への問い合わせは空リスト。"""
        assert store.list_uncompleted_by_being(BeingId("missing")) == []

    def test_完了済み_memo_は_含まれない(self, store: InMemoryMemoStore) -> None:
        """complete 済みの memo は list_uncompleted から除外される。"""
        m1 = store.add_by_being(BeingId("ada"), "未完了")
        m2 = store.add_by_being(BeingId("ada"), "完了する")
        store.complete_by_being(BeingId("ada"), m2)
        entries = store.list_uncompleted_by_being(BeingId("ada"))
        assert {e.id for e in entries} == {m1}

    def test_並び順は_added_at_の新しい順(self, store: InMemoryMemoStore) -> None:
        """新しい memo が前に来る並び (旧 API と同じ)。"""
        store.add_by_being(BeingId("ada"), "古い")
        store.add_by_being(BeingId("ada"), "新しい")
        entries = store.list_uncompleted_by_being(BeingId("ada"))
        assert entries[0].content == "新しい"
        assert entries[1].content == "古い"


class TestCompleteByBeing:
    """complete_by_being の挙動。"""

    def test_存在する_memo_を完了できる(self, store: InMemoryMemoStore) -> None:
        """正常系: True が返り、list_uncompleted から消える。"""
        memo_id = store.add_by_being(BeingId("ada"), "完了する")
        assert store.complete_by_being(BeingId("ada"), memo_id) is True
        assert store.list_uncompleted_by_being(BeingId("ada")) == []

    def test_存在しない_memo_を完了しようとすると_False(
        self, store: InMemoryMemoStore
    ) -> None:
        """未登録 memo_id への complete は False。"""
        assert (
            store.complete_by_being(BeingId("ada"), "missing-id") is False
        )

    def test_fulfillment_context_を渡すと_保存される(
        self, store: InMemoryMemoStore
    ) -> None:
        """fulfillment_context が memo entry に格納される。"""
        memo_id = store.add_by_being(BeingId("ada"), "完了する")
        from datetime import datetime

        ctx = MemoFulfillmentContext(
            completed_at=datetime.now(),
            completed_at_tick=10,
            recent_observation_proses=("obs1",),
            recent_action_summaries=("act1",),
        )
        store.complete_by_being(BeingId("ada"), memo_id, fulfillment_context=ctx)
        # 完了 entry を外から確認する public API が現状無いため、内部 store を直接
        # 検査する (= MemoRepository に list_all を生やすのは YAGNI / 旧 API 側も
        # 同じパターンに揃える)。Step 4 で BeingSnapshot に memo payload を載せる
        # 際、完了済み entry の取り出し公道ができたら本テストはそちらに置換可能。
        all_entries = store._being_store[BeingId("ada")]  # noqa: SLF001
        assert all_entries[0].fulfillment_context == ctx

    def test_being_id_型違反は_TypeError(self, store: InMemoryMemoStore) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="being_id"):
            store.complete_by_being("ada", "id")  # type: ignore[arg-type]


class TestRemoveByBeing:
    """remove_by_being の挙動。"""

    def test_存在する_memo_を削除できる(self, store: InMemoryMemoStore) -> None:
        """正常系: True が返り list から消える。"""
        memo_id = store.add_by_being(BeingId("ada"), "削除する")
        assert store.remove_by_being(BeingId("ada"), memo_id) is True
        assert store.list_uncompleted_by_being(BeingId("ada")) == []

    def test_存在しない_memo_の削除は_False(self, store: InMemoryMemoStore) -> None:
        """未登録 memo_id への remove は False。"""
        assert store.remove_by_being(BeingId("ada"), "missing") is False

    def test_複数_memo_を順番に削除しても_他は残る(
        self, store: InMemoryMemoStore
    ) -> None:
        """1 件削除しても残りの memo は影響を受けない (index reindex の正しさ)。"""
        m1 = store.add_by_being(BeingId("ada"), "1")
        m2 = store.add_by_being(BeingId("ada"), "2")
        m3 = store.add_by_being(BeingId("ada"), "3")
        store.remove_by_being(BeingId("ada"), m2)
        # 残った m1 / m3 はどちらも引き続き complete / remove できる
        assert store.complete_by_being(BeingId("ada"), m1) is True
        assert store.remove_by_being(BeingId("ada"), m3) is True


class TestListAllByBeing:
    """list_all_by_being の挙動 (Phase 4 Step 4-2a)。"""

    def test_未完了と完了済の両方を返す(self, store: InMemoryMemoStore) -> None:
        """``list_uncompleted_by_being`` と違い、完了済も含めて全件返す。"""
        b = BeingId("ada")
        m1 = store.add_by_being(b, "active")
        m2 = store.add_by_being(b, "done")
        store.complete_by_being(b, m2)
        all_entries = store.list_all_by_being(b)
        ids = [e.id for e in all_entries]
        assert set(ids) == {m1, m2}

    def test_未登録_being_は空リスト(self, store: InMemoryMemoStore) -> None:
        """未知の being には空リストを返す。"""
        assert store.list_all_by_being(BeingId("missing")) == []

    def test_being_id_型違いは_TypeError(self, store: InMemoryMemoStore) -> None:
        with pytest.raises(TypeError):
            store.list_all_by_being("ada")  # type: ignore[arg-type]


class TestReplaceAllByBeing:
    """replace_all_by_being の挙動 (Phase 4 Step 4-2a, snapshot restore primitive)。"""

    def test_既存_memo_は全削除されて_entries_で置換される(
        self, store: InMemoryMemoStore
    ) -> None:
        """destructive overwrite。entries の通りに再構築。"""
        from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
        from datetime import datetime

        b = BeingId("ada")
        store.add_by_being(b, "old")
        new_entries = [
            MemoEntry(id="m-new", content="new", added_at=datetime.now(), completed=False),
        ]
        store.replace_all_by_being(b, new_entries)
        listed = store.list_all_by_being(b)
        assert [e.id for e in listed] == ["m-new"]

    def test_空リストでクリアできる(self, store: InMemoryMemoStore) -> None:
        """``entries=[]`` で being 配下を空にできる。"""
        b = BeingId("ada")
        store.add_by_being(b, "x")
        store.replace_all_by_being(b, [])
        assert store.list_all_by_being(b) == []

    def test_replace_後の_memo_は_complete_remove_で操作可能(
        self, store: InMemoryMemoStore
    ) -> None:
        """index 再構築が正しく、id ベースで complete / remove が引ける。"""
        from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
        from datetime import datetime

        b = BeingId("ada")
        entries = [
            MemoEntry(id="m-a", content="A", added_at=datetime.now(), completed=False),
            MemoEntry(id="m-b", content="B", added_at=datetime.now(), completed=False),
        ]
        store.replace_all_by_being(b, entries)
        assert store.complete_by_being(b, "m-a") is True
        assert store.remove_by_being(b, "m-b") is True

    def test_entries_に_非_MemoEntry_が混ざると_TypeError(
        self, store: InMemoryMemoStore
    ) -> None:
        with pytest.raises(TypeError):
            store.replace_all_by_being(BeingId("ada"), ["not-an-entry"])  # type: ignore[list-item]


# Phase 3 Step 3a-3: 旧 player_id API を撤去したため「新旧独立性」テストは削除済。
# 撤去前は ``_store`` (player_id keyed) と ``_being_store`` (being_id keyed) の
# 独立性を検証していたが、player_id 経路 (add / list_uncompleted / complete /
# remove) がなくなった現在は being_id 経路しか存在しない。
