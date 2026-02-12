import logging
from typing import Optional, Tuple, Callable, Any, TYPE_CHECKING
from functools import wraps

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.repository import UserRepository
from ai_rpg_world.domain.sns.aggregate import UserAggregate
from ai_rpg_world.application.social.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand
)
from ai_rpg_world.application.social.exceptions import (
    SystemErrorException,
    UserCommandException,
    ApplicationExceptionFactory,
)
from ai_rpg_world.application.social.exceptions.command.user_command_exception import UserNotFoundForCommandException
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException
from ai_rpg_world.application.social.contracts.dtos import CommandResultDto, ErrorResponseDto
from ai_rpg_world.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from ai_rpg_world.domain.sns.service.relationship_domain_service import RelationshipDomainService


class UserCommandService:
    """ユーザーコマンドサービス"""

    def __init__(self, user_repository: UserRepository, event_publisher: EventPublisher, unit_of_work: UnitOfWork):
        self.user_repository = user_repository
        self.event_publisher = event_publisher
        self._unit_of_work = unit_of_work
        self.logger = logging.getLogger(self.__class__.__name__)
        self._register_event_handlers()

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except ApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except SnsDomainException as e:
            raise ApplicationExceptionFactory.create_from_domain_exception(
                e,
                user_id=context.get('user_id'),
                target_user_id=context.get('target_user_id')
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)
    
    def _register_event_handlers(self) -> None:
        """イベントハンドラーを登録, 現在はsns関連のイベントハンドラは未実装"""
        pass



    def create_user(self, command: CreateUserCommand) -> CommandResultDto:
        """ユーザーの新規作成"""
        return self._execute_with_error_handling(
            operation=lambda: self._create_user_impl(command),
            context={
                "action": "create_user",
                "user_name": command.user_name
            }
        )

    def _create_user_impl(self, command: CreateUserCommand) -> CommandResultDto:
        """ユーザーの新規作成の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_id = self.user_repository.generate_user_id()
            user_aggregate = UserAggregate.create_new_user(user_id, command.user_name, command.display_name, command.bio)

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーが正常に作成されました: user_id={user_id}, user_name={command.user_name}",
            extra={
                "user_id": user_id,
                "user_name": command.user_name,
                "action": "create_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーが正常に作成されました",
            data={"user_id": user_id}
        )

    def update_user_profile(self, command: UpdateUserProfileCommand) -> CommandResultDto:
        """ユーザープロフィールの更新"""
        return self._execute_with_error_handling(
            operation=lambda: self._update_user_profile_impl(command),
            context={
                "action": "update_user_profile",
                "user_id": command.user_id
            }
        )

    def _update_user_profile_impl(self, command: UpdateUserProfileCommand) -> CommandResultDto:
        """ユーザープロフィールの更新の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.user_id, "update_user_profile")

            user_aggregate.update_user_profile(command.new_bio, command.new_display_name)

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザープロフィールが正常に更新されました: user_id={command.user_id}",
            extra={
                "user_id": command.user_id,
                "action": "update_user_profile"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザープロフィールが正常に更新されました",
            data={"user_id": command.user_id}
        )

    def follow_user(self, command: FollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー"""
        return self._execute_with_error_handling(
            operation=lambda: self._follow_user_impl(command),
            context={
                "action": "follow_user",
                "user_id": command.follower_user_id,
                "target_user_id": command.followee_user_id
            }
        )

    def _follow_user_impl(self, command: FollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.follower_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.follower_user_id, "follow_user")

            # フォローされるユーザーが存在するかチェック
            followee_aggregate = self.user_repository.find_by_id(UserId(command.followee_user_id))
            if followee_aggregate is None:
                raise UserNotFoundForCommandException(command.followee_user_id, "follow_user")

            # ドメインサービスでフォロー可能かどうかをチェック
            RelationshipDomainService.can_follow(user_aggregate, followee_aggregate)

            user_aggregate.follow(UserId(command.followee_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーをフォローしました: follower={command.follower_user_id}, followee={command.followee_user_id}",
            extra={
                "follower_user_id": command.follower_user_id,
                "followee_user_id": command.followee_user_id,
                "action": "follow_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーをフォローしました",
            data={
                "follower_user_id": command.follower_user_id,
                "followee_user_id": command.followee_user_id
            }
        )

    def unfollow_user(self, command: UnfollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー解除"""
        return self._execute_with_error_handling(
            operation=lambda: self._unfollow_user_impl(command),
            context={
                "action": "unfollow_user",
                "user_id": command.follower_user_id,
                "target_user_id": command.followee_user_id
            }
        )

    def _unfollow_user_impl(self, command: UnfollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー解除の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.follower_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.follower_user_id, "unfollow_user")

            user_aggregate.unfollow(UserId(command.followee_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーのフォローを解除しました: follower={command.follower_user_id}, followee={command.followee_user_id}",
            extra={
                "follower_user_id": command.follower_user_id,
                "followee_user_id": command.followee_user_id,
                "action": "unfollow_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーのフォローを解除しました",
            data={
                "follower_user_id": command.follower_user_id,
                "followee_user_id": command.followee_user_id
            }
        )

    def block_user(self, command: BlockUserCommand) -> CommandResultDto:
        """ユーザーブロック"""
        return self._execute_with_error_handling(
            operation=lambda: self._block_user_impl(command),
            context={
                "action": "block_user",
                "user_id": command.blocker_user_id,
                "target_user_id": command.blocked_user_id
            }
        )

    def _block_user_impl(self, command: BlockUserCommand) -> CommandResultDto:
        """ユーザーブロックの実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.blocker_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.blocker_user_id, "block_user")

            user_aggregate.block(UserId(command.blocked_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーをブロックしました: blocker={command.blocker_user_id}, blocked={command.blocked_user_id}",
            extra={
                "blocker_user_id": command.blocker_user_id,
                "blocked_user_id": command.blocked_user_id,
                "action": "block_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーをブロックしました",
            data={
                "blocker_user_id": command.blocker_user_id,
                "blocked_user_id": command.blocked_user_id
            }
        )

    def unblock_user(self, command: UnblockUserCommand) -> CommandResultDto:
        """ユーザーブロック解除"""
        return self._execute_with_error_handling(
            operation=lambda: self._unblock_user_impl(command),
            context={
                "action": "unblock_user",
                "user_id": command.blocker_user_id,
                "target_user_id": command.blocked_user_id
            }
        )

    def _unblock_user_impl(self, command: UnblockUserCommand) -> CommandResultDto:
        """ユーザーブロック解除の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.blocker_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.blocker_user_id, "unblock_user")

            user_aggregate.unblock(UserId(command.blocked_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーのブロックを解除しました: blocker={command.blocker_user_id}, blocked={command.blocked_user_id}",
            extra={
                "blocker_user_id": command.blocker_user_id,
                "blocked_user_id": command.blocked_user_id,
                "action": "unblock_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーのブロックを解除しました",
            data={
                "blocker_user_id": command.blocker_user_id,
                "blocked_user_id": command.blocked_user_id
            }
        )

    def subscribe_user(self, command: SubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読"""
        return self._execute_with_error_handling(
            operation=lambda: self._subscribe_user_impl(command),
            context={
                "action": "subscribe_user",
                "user_id": command.subscriber_user_id,
                "target_user_id": command.subscribed_user_id
            }
        )

    def _subscribe_user_impl(self, command: SubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.subscriber_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.subscriber_user_id, "subscribe_user")

            # 購読されるユーザーが存在するかチェック
            subscribed_aggregate = self.user_repository.find_by_id(UserId(command.subscribed_user_id))
            if subscribed_aggregate is None:
                raise UserNotFoundForCommandException(command.subscribed_user_id, "subscribe_user")

            # ドメインサービスで購読可能かどうかをチェック
            RelationshipDomainService.can_subscribe(user_aggregate, subscribed_aggregate)

            user_aggregate.subscribe(UserId(command.subscribed_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーを購読しました: subscriber={command.subscriber_user_id}, subscribed={command.subscribed_user_id}",
            extra={
                "subscriber_user_id": command.subscriber_user_id,
                "subscribed_user_id": command.subscribed_user_id,
                "action": "subscribe_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーを購読しました",
            data={
                "subscriber_user_id": command.subscriber_user_id,
                "subscribed_user_id": command.subscribed_user_id
            }
        )

    def unsubscribe_user(self, command: UnsubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読解除"""
        return self._execute_with_error_handling(
            operation=lambda: self._unsubscribe_user_impl(command),
            context={
                "action": "unsubscribe_user",
                "user_id": command.subscriber_user_id,
                "target_user_id": command.subscribed_user_id
            }
        )

    def _unsubscribe_user_impl(self, command: UnsubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読解除の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_aggregate = self.user_repository.find_by_id(UserId(command.subscriber_user_id))
            if user_aggregate is None:
                raise UserNotFoundForCommandException(command.subscriber_user_id, "unsubscribe_user")

            user_aggregate.unsubscribe(UserId(command.subscribed_user_id))

            # リポジトリに保存
            self.user_repository.save(user_aggregate)

        self.logger.info(
            f"ユーザーの購読を解除しました: subscriber={command.subscriber_user_id}, subscribed={command.subscribed_user_id}",
            extra={
                "subscriber_user_id": command.subscriber_user_id,
                "subscribed_user_id": command.subscribed_user_id,
                "action": "unsubscribe_user"
            }
        )

        return CommandResultDto(
            success=True,
            message="ユーザーの購読を解除しました",
            data={
                "subscriber_user_id": command.subscriber_user_id,
                "subscribed_user_id": command.subscribed_user_id
            }
        )