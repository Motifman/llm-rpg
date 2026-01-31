from typing import List
from ai_rpg_world.domain.common.notifier import Notifier


class ConsoleNotifier(Notifier):
    """コンソール出力による通知の実装"""

    def send_notification(self, recipient_id: int, message: str):
        """単一の受信者に通知を送信"""
        print(f"[NOTIFICATION] Player {recipient_id}: {message}")

    def send_notification_to_all(self, recipient_ids: List[int], message: str):
        """複数の受信者に通知を送信"""
        for recipient_id in recipient_ids:
            self.send_notification(recipient_id, message)
