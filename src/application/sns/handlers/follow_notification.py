from src.domain.common.event_handler import EventHandler
from src.domain.sns.event import SnsUserFollowedEvent
from src.domain.sns.repository import UserRepository, SnsNotificationRepository


class FollowNotificationHandler(EventHandler[SnsUserFollowedEvent]):
    def __init__(self, sns_user_repository: UserRepository, sns_notification_repository: SnsNotificationRepository):
        self._sns_user_repository = sns_user_repository
        self._sns_notification_repository = sns_notification_repository

    def handle(self, event: SnsUserFollowedEvent):
        pass