"""InMemoryDataStoreのtransaction snapshotが全業務状態を復元することを保証する。"""

from __future__ import annotations

from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
    InMemoryDataStore,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class TestInMemoryDataStoreSnapshot:
    """snapshotの構造網羅と復元時の防御コピーを検証する。"""

    def test_snapshot_covers_every_public_state_attribute(self) -> None:
        """業務状態の属性追加時はsnapshotへ自動的に含め、私有transaction属性は除外する。"""
        store = InMemoryDataStore()

        snapshot = store.take_snapshot()

        expected = {name for name in vars(store) if not name.startswith("_uow_")}
        assert set(snapshot) == expected
        assert not any(name.startswith("_uow_") for name in snapshot)

    def test_restore_recovers_profiles_notifications_mappings_and_id_counters(
        self,
    ) -> None:
        """従来欠落していたプロフィール・通知・索引・採番値もrollbackで元に戻す。"""
        store = InMemoryDataStore()
        store.player_profiles[object()] = {"name": "before"}  # type: ignore[index]
        store.sns_notifications[object()] = {"message": "before"}  # type: ignore[index]
        store.sns_username_to_user_id["before"] = object()  # type: ignore[assignment]
        store.next_player_id = 41
        store.next_trade_id = 42
        store.next_item_instance_id = 43
        snapshot = store.take_snapshot()

        store.player_profiles.clear()
        store.sns_notifications.clear()
        store.sns_username_to_user_id.clear()
        store.next_player_id = 101
        store.next_trade_id = 102
        store.next_item_instance_id = 103
        store.restore_snapshot(snapshot)

        assert list(store.player_profiles.values()) == [{"name": "before"}]
        assert list(store.sns_notifications.values()) == [{"message": "before"}]
        assert "before" in store.sns_username_to_user_id
        assert store.next_player_id == 41
        assert store.next_trade_id == 42
        assert store.next_item_instance_id == 43

    def test_restore_rejects_incomplete_snapshot_without_partial_update(self) -> None:
        """項目不足のsnapshotは1項目も書き戻す前に拒否する。"""
        store = InMemoryDataStore()
        store.next_player_id = 7
        snapshot = store.take_snapshot()
        del snapshot["next_player_id"]

        try:
            store.restore_snapshot(snapshot)
        except RuntimeError as error:
            assert "missing=['next_player_id']" in str(error)
        else:
            raise AssertionError("不完全snapshotが受理されました")

        assert store.next_player_id == 7

    def test_uow_rollback_restores_repository_id_generation(self) -> None:
        """即時に採番値を進める既存repository操作もUoW rollbackで元へ戻す。"""
        store = InMemoryDataStore()
        uow = InMemoryUnitOfWork(data_store=store)
        repository = InMemoryPlayerProfileRepository(store, uow)
        original_next_id = store.next_player_id
        uow.begin()

        generated = repository.generate_id()
        assert generated.value == original_next_id
        assert store.next_player_id == original_next_id + 1
        uow.rollback()

        assert store.next_player_id == original_next_id
