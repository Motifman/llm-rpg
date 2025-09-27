import logging
from typing import Optional, Tuple, Callable, Any
from functools import wraps
from src.domain.common.event_publisher import EventPublisher
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.repository import UserRepository
from src.domain.sns.aggregate import UserAggregate
from src.application.sns.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand
)
from src.application.sns.exceptions import (
    SystemErrorException,
    UserCommandException,
    ApplicationExceptionFactory,
)
from src.application.sns.exceptions.command.user_command_exception import UserNotFoundForCommandException
from src.application.sns.exceptions.base_exception import ApplicationException
from src.application.sns.contracts.dtos import CommandResultDto, ErrorResponseDto
from src.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from src.domain.sns.service.relationship_domain_service import RelationshipDomainService


class UserCommandService:
    """ユーザーコマンドサービス"""

    def __init__(self, user_repository: UserRepository, event_publisher: EventPublisher):
        self.user_repository = user_repository
        self.event_publisher = event_publisher
        self.logger = logging.getLogger(self.__class__.__name__)
        self._register_event_handlers()
    
    def _register_event_handlers(self) -> None:
        """イベントハンドラーを登録, 現在はsns関連のイベントハンドラは未実装"""
        pass

    def _handle_domain_exception(self, exception: SnsDomainException, user_id: Optional[int] = None, target_user_id: Optional[int] = None) -> ErrorResponseDto:
        """ドメイン例外を適切なエラーレスポンスに変換"""
        # デフォルトのエラーコードとメッセージを取得
        error_code, message = self._get_error_info_from_exception(exception)

        # ログに記録
        self.logger.warning(
            f"ドメイン例外が発生: {error_code} - {message}",
            extra={
                "error_type": type(exception).__name__,
                "user_id": user_id,
                "target_user_id": target_user_id,
                "exception_message": str(exception),
            }
        )

        return ErrorResponseDto(
            error_code=error_code,
            message=message,
            details=str(exception),
            user_id=user_id,
            target_user_id=target_user_id,
        )

    def _get_error_info_from_exception(self, exception: SnsDomainException) -> tuple[str, str]:
        """例外の種類に基づいてエラーコードとメッセージを取得"""
        # Exceptionクラスに定義されたエラーコードを使用
        error_code = getattr(exception, 'error_code', 'UNKNOWN_ERROR')
        message = str(exception)

        return error_code, message

    def _convert_to_application_exception(self, domain_exception: SnsDomainException, user_id: Optional[int] = None, target_user_id: Optional[int] = None) -> UserCommandException:
        """ドメイン例外をアプリケーション例外に変換（簡素化）"""
        return ApplicationExceptionFactory.create_from_domain_exception(
            domain_exception,
            user_id=user_id,
            target_user_id=target_user_id
        )

    def _get_user_ids_from_command(self, command: Any) -> Tuple[Optional[int], Optional[int]]:
        """コマンドからユーザーIDを取得"""
        user_id = getattr(command, 'user_id', None)
        target_user_id = None

        # 各コマンドタイプに応じてtarget_user_idを取得
        if hasattr(command, 'follower_user_id'):
            user_id = command.follower_user_id
            target_user_id = getattr(command, 'followee_user_id', None)
        elif hasattr(command, 'blocker_user_id'):
            user_id = command.blocker_user_id
            target_user_id = getattr(command, 'blocked_user_id', None)
        elif hasattr(command, 'subscriber_user_id'):
            user_id = command.subscriber_user_id
            target_user_id = getattr(command, 'subscribed_user_id', None)

        return user_id, target_user_id

    def handle_domain_exceptions(method: Callable) -> Callable:
        """ドメイン例外とアプリケーション例外を処理するデコレータ"""
        @wraps(method)
        def wrapper(self, command: Any, *args, **kwargs):
            try:
                return method(self, command, *args, **kwargs)
            except ApplicationException as e:
                # アプリケーション例外はそのまま再スロー
                raise e
            except SnsDomainException as e:
                user_id, target_user_id = self._get_user_ids_from_command(command)
                app_exception = self._convert_to_application_exception(e, user_id=user_id, target_user_id=target_user_id)
                error_response = self._handle_domain_exception(e, user_id=user_id, target_user_id=target_user_id)
                self.logger.error(f"{method.__name__} failed: {error_response.message}", extra={"error": error_response})
                raise app_exception
            except Exception as e:
                user_id, target_user_id = self._get_user_ids_from_command(command)
                self.logger.error(f"Unexpected error in {method.__name__}: {str(e)}", extra={
                    "user_id": user_id,
                    "target_user_id": target_user_id,
                    "action": method.__name__
                })
                raise SystemErrorException(f"{method.__name__} failed: {str(e)}", original_exception=e)
        return wrapper

    @handle_domain_exceptions
    def create_user(self, command: CreateUserCommand) -> CommandResultDto:
        """ユーザーの新規作成"""
        user_id = self.user_repository.generate_user_id()
        user_aggregate = UserAggregate.create_new_user(user_id, command.user_name, command.display_name, command.bio)
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def update_user_profile(self, command: UpdateUserProfileCommand) -> CommandResultDto:
        """ユーザープロフィールの更新"""
        user_aggregate = self.user_repository.find_by_id(UserId(command.user_id))
        if user_aggregate is None:
            raise UserNotFoundForCommandException(command.user_id, "update_user_profile")

        user_aggregate.update_user_profile(command.new_bio, command.new_display_name)
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def follow_user(self, command: FollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー"""
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
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def unfollow_user(self, command: UnfollowUserCommand) -> CommandResultDto:
        """ユーザーフォロー解除"""
        user_aggregate = self.user_repository.find_by_id(UserId(command.follower_user_id))
        if user_aggregate is None:
            raise UserNotFoundForCommandException(command.follower_user_id, "unfollow_user")

        user_aggregate.unfollow(UserId(command.followee_user_id))
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def block_user(self, command: BlockUserCommand) -> CommandResultDto:
        """ユーザーブロック"""
        user_aggregate = self.user_repository.find_by_id(UserId(command.blocker_user_id))
        if user_aggregate is None:
            raise UserNotFoundForCommandException(command.blocker_user_id, "block_user")

        user_aggregate.block(UserId(command.blocked_user_id))
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def unblock_user(self, command: UnblockUserCommand) -> CommandResultDto:
        """ユーザーブロック解除"""
        user_aggregate = self.user_repository.find_by_id(UserId(command.blocker_user_id))
        if user_aggregate is None:
            raise UserNotFoundForCommandException(command.blocker_user_id, "unblock_user")

        user_aggregate.unblock(UserId(command.blocked_user_id))
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def subscribe_user(self, command: SubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読"""
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
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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

    @handle_domain_exceptions
    def unsubscribe_user(self, command: UnsubscribeUserCommand) -> CommandResultDto:
        """ユーザー購読解除"""
        user_aggregate = self.user_repository.find_by_id(UserId(command.subscriber_user_id))
        if user_aggregate is None:
            raise UserNotFoundForCommandException(command.subscriber_user_id, "unsubscribe_user")

        user_aggregate.unsubscribe(UserId(command.subscribed_user_id))
        self.event_publisher.publish_all(user_aggregate.get_events())
        user_aggregate.clear_events()
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