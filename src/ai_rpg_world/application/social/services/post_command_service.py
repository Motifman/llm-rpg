import logging
from typing import Optional, Tuple, Callable, Any, TYPE_CHECKING
from functools import wraps

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.sns.value_object import UserId, PostId
from ai_rpg_world.domain.sns.repository import PostRepository, UserRepository
from ai_rpg_world.domain.sns.aggregate import PostAggregate
from ai_rpg_world.domain.sns.value_object import PostContent
from ai_rpg_world.application.social.contracts.commands import (
    CreatePostCommand,
    LikePostCommand,
    DeletePostCommand
)
from ai_rpg_world.application.social.contracts.dtos import CommandResultDto, ErrorResponseDto
from ai_rpg_world.application.social.exceptions import ApplicationException
from ai_rpg_world.application.social.exceptions.command.post_command_exception import (
    PostCommandException,
    PostCreationException,
    PostDeletionException,
    PostLikeException,
    PostNotFoundForCommandException,
)
from ai_rpg_world.application.social.exceptions import ApplicationExceptionFactory
from ai_rpg_world.application.social.exceptions import SystemErrorException
from ai_rpg_world.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)


class PostCommandService:
    """ポストコマンドサービス"""

    def __init__(self, post_repository: PostRepository, user_repository: UserRepository, event_publisher: EventPublisher, unit_of_work: UnitOfWork):
        self._post_repository = post_repository
        self._user_repository = user_repository
        self._event_publisher = event_publisher
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

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
                post_id=context.get('post_id')
            )
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def create_post(self, command: CreatePostCommand) -> CommandResultDto:
        """ポストを作成"""
        return self._execute_with_error_handling(
            operation=lambda: self._create_post_impl(command),
            context={
                "action": "create_post",
                "user_id": command.user_id
            }
        )

    def _create_post_impl(self, command: CreatePostCommand) -> CommandResultDto:
        """ポストを作成の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # PostContentの作成（ハッシュタグはドメイン層で自動抽出）
            post_content = PostContent.create(command.content, command.visibility)

            # PostAggregateの作成
            post_id = self._post_repository.generate_post_id()
            post_aggregate = PostAggregate.create(post_id, UserId(command.user_id), post_content)

            # リポジトリに保存
            self._post_repository.save(post_aggregate)

            self._logger.info(f"Post created successfully: post_id={post_id.value}, user_id={command.user_id}")

            return CommandResultDto(
                success=True,
                message="ポストが正常に作成されました",
                data={"post_id": post_id.value}
            )

    def like_post(self, command: LikePostCommand) -> CommandResultDto:
        """ポストにいいね"""
        return self._execute_with_error_handling(
            operation=lambda: self._like_post_impl(command),
            context={
                "action": "like_post",
                "user_id": command.user_id,
                "post_id": command.post_id
            }
        )

    def _like_post_impl(self, command: LikePostCommand) -> CommandResultDto:
        """ポストにいいねの実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # ポストの取得
            post_aggregate = self._post_repository.find_by_id(command.post_id)
            if post_aggregate is None:
                raise PostNotFoundForCommandException(command.post_id, "like_post")

            # いいね実行
            post_aggregate.like_post(UserId(command.user_id))

            # リポジトリに保存
            self._post_repository.save(post_aggregate)

            self._logger.info(f"Post liked successfully: post_id={command.post_id}, user_id={command.user_id}")

            return CommandResultDto(
                success=True,
                message="ポストにいいねしました",
                data={"post_id": command.post_id, "user_id": command.user_id}
            )

    def delete_post(self, command: DeletePostCommand) -> CommandResultDto:
        """ポストを削除"""
        return self._execute_with_error_handling(
            operation=lambda: self._delete_post_impl(command),
            context={
                "action": "delete_post",
                "user_id": command.user_id,
                "post_id": command.post_id
            }
        )

    def _delete_post_impl(self, command: DeletePostCommand) -> CommandResultDto:
        """ポストを削除の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # ポストの取得
            post_aggregate = self._post_repository.find_by_id(command.post_id)
            if post_aggregate is None:
                raise PostNotFoundForCommandException(command.post_id, "delete_post")

            # 削除実行（所有権チェックはドメイン層で実施）
            post_aggregate.delete_post(UserId(command.user_id))

            # リポジトリに保存
            self._post_repository.save(post_aggregate)

            self._logger.info(f"Post deleted successfully: post_id={command.post_id}, user_id={command.user_id}")

            return CommandResultDto(
                success=True,
                message="ポストが正常に削除されました",
                data={"post_id": command.post_id, "user_id": command.user_id}
        )
