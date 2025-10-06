"""
InMemorySnsNotificationRepositoryWithUow - Unit of Workと統合されたインメモリSNS通知レポジトリ
"""
from typing import List, Optional, Dict, Tuple, Set, Callable
from src.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemorySnsNotificationRepositoryWithUow(InMemorySnsNotificationRepository):
    """Unit of Workと統合されたNotificationを使用するインメモリリポジトリ"""

    def __init__(self, unit_of_work: InMemoryUnitOfWork):
        # 親クラスの初期化をスキップして手動で初期化
        self._notifications: Dict = {}
        from src.domain.sns.value_object.notification_id import NotificationId
        self._next_notification_id = NotificationId(1)
        self._unit_of_work = unit_of_work

    def clear(self) -> None:
        """全通知をクリア（テスト用）"""
        self._notifications.clear()
        from src.domain.sns.value_object.notification_id import NotificationId
        self._next_notification_id = NotificationId(1)

    def save(self, notification):
        """通知を保存（Unit of Work対応版）"""
        def save_operation():
            self._notifications[notification.notification_id] = notification

        # トランザクション内でのみ保存可能
        if self._unit_of_work.is_in_transaction():
            # イベントハンドラー内では直接保存（コミット時にクリアされるため）
            if self._unit_of_work.get_pending_events():  # イベント処理中かどうかを確認
                save_operation()
            else:
                self._unit_of_work.add_operation(save_operation)
        else:
            # トランザクション外の場合は即時実行（テスト用）
            save_operation()

        return notification

    def mark_as_read(self, notification_id):
        """通知を既読にする（Unit of Work対応版）"""
        def mark_operation():
            notification = self._notifications.get(notification_id)
            if notification:
                notification.mark_as_read()

        # トランザクション内でのみ実行可能
        if self._unit_of_work.is_in_transaction():
            self._unit_of_work.add_operation(mark_operation)
        else:
            # トランザクション外の場合は即時実行（テスト用）
            mark_operation()

    def mark_all_as_read(self, user_id):
        """ユーザーの全通知を既読にする（Unit of Work対応版）"""
        def mark_all_operation():
            for notification in self._notifications.values():
                if notification.user_id == user_id:
                    notification.mark_as_read()

        # トランザクション内でのみ実行可能
        if self._unit_of_work.is_in_transaction():
            self._unit_of_work.add_operation(mark_all_operation)
        else:
            # トランザクション外の場合は即時実行（テスト用）
            mark_all_operation()

    def find_by_ids(self, notification_ids):
        """IDのリストで通知を検索（Unit of Work対応版）"""
        def find_operation():
            return [
                self._notifications[notification_id]
                for notification_id in notification_ids
                if notification_id in self._notifications
            ]

        # トランザクション内では即時実行
        if self._unit_of_work.is_in_transaction():
            return find_operation()
        else:
            # トランザクション外の場合は即時実行（テスト用）
            return find_operation()

    def delete(self, notification_id):
        """通知を削除（Unit of Work対応版）"""
        def delete_operation():
            if notification_id in self._notifications:
                del self._notifications[notification_id]
                return True
            return False

        # トランザクション内でのみ実行可能
        if self._unit_of_work.is_in_transaction():
            self._unit_of_work.add_operation(delete_operation)
            # 削除操作の結果を即時返す（実際の削除はコミット時）
            return delete_operation()
        else:
            # トランザクション外の場合は即時実行（テスト用）
            return delete_operation()

    def find_all(self):
        """全ての通知を取得（Unit of Work対応版）"""
        def find_all_operation():
            return list(self._notifications.values())

        # トランザクション内では即時実行
        if self._unit_of_work.is_in_transaction():
            return find_all_operation()
        else:
            # トランザクション外の場合は即時実行（テスト用）
            return find_all_operation()
