from abc import ABC, abstractmethod
from typing import List


class Notifier(ABC):
    @abstractmethod
    def send_notification(self, recipient_id: int, message: str):
        pass
    
    @abstractmethod
    def send_notification_to_all(self, recipient_ids: List[int], message: str):
        pass
