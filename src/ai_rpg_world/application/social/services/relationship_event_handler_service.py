import logging
from typing import TYPE_CHECKING, Callable, Any
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.sns.event import SnsUserBlockedEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import SnsUserRepository


class RelationshipEventHandlerService:
    """関係管理イベントハンドラサービス"""

    def __init__(
        self,
        user_repository: "SnsUserRepository",
        unit_of_work_factory: UnitOfWorkFactory
    ):
        self._user_repository = user_repository
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(self, operation: Callable[[], Any], context: dict) -> None:
        """別トランザクションで操作を実行し、共通の例外処理を行う"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except Exception as e:
            # イベントハンドラなので、例外を再スローせず処理を継続
            self._logger.error(f"Failed to handle event in {context.get('handler', 'unknown')}: {str(e)}",
                             extra=context, exc_info=True)
            
    def handle_user_blocked(self, event: SnsUserBlockedEvent) -> None:
        """ユーザーブロック時の関係解除処理"""
        self._logger.info(f"Processing user blocked event: blocker={event.blocker_user_id}, blocked={event.blocked_user_id}")

        def operation():
            # ブロックされたユーザー（blocked_user）がブロックしたユーザー（blocker_user）を
            # フォローまたはサブスクライブしている場合、関係を解除する
            blocked_user = self._user_repository.find_by_id(event.blocked_user_id)
            if blocked_user is None:
                self._logger.warning(f"Blocked user not found: {event.blocked_user_id}")
                return

            blocker_user = self._user_repository.find_by_id(event.blocker_user_id)
            if blocker_user is None:
                self._logger.warning(f"Blocker user not found: {event.blocker_user_id}")
                return

            relations_removed = 0

            # ブロックされた側がブロックした側をフォローしている場合、フォロー解除
            if blocked_user.is_following(event.blocker_user_id):
                blocked_user.unfollow(event.blocker_user_id)
                relations_removed += 1
                self._logger.debug(f"Removed follow relationship: {event.blocked_user_id} -> {event.blocker_user_id}")

            # ブロックされた側がブロックした側をサブスクライブしている場合、サブスクライブ解除
            if blocked_user.is_subscribed(event.blocker_user_id):
                blocked_user.unsubscribe(event.blocker_user_id)
                relations_removed += 1
                self._logger.debug(f"Removed subscribe relationship: {event.blocked_user_id} -> {event.blocker_user_id}")

            # 関係が変更された場合のみ保存
            if relations_removed > 0:
                self._user_repository.save(blocked_user)
                self._logger.info(f"Successfully removed {relations_removed} relationships due to user block: {event.blocked_user_id} -> {event.blocker_user_id}")
            else:
                self._logger.debug(f"No relationships to remove for blocked user: {event.blocked_user_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_user_blocked",
            "blocker_id": event.blocker_user_id,
            "blocked_id": event.blocked_user_id
        })
