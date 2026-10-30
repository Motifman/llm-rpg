import logging
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate

from ai_rpg_world.application.common.execution_provenance import current_execution_provenance
from ai_rpg_world.application.social.contracts.commands import CreateReplyCommand, DeleteReplyCommand, LikeReplyCommand
from ai_rpg_world.application.social.contracts.dtos import CommandResultDto, ErrorResponseDto
from ai_rpg_world.application.social.exceptions import (
    ApplicationException,
    ApplicationExceptionFactory,
    SystemErrorException,
)
from ai_rpg_world.application.social.exceptions.command.reply_command_exception import (
    ReplyCommandException,
    ReplyCreationException,
    ReplyDeletionException,
    ReplyLikeException,
    ReplyNotFoundForCommandException,
    ReplyOwnershipException,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.sns.aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.exception import (
    ContentOwnershipException,
    SnsDomainException,
    UserNotFoundException,
)
from ai_rpg_world.domain.sns.repository import PostRepository, ReplyRepository, UserRepository
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId

_Result = TypeVar("_Result")


class ReplyCommandService:
    """リプライコマンドサービス"""

    def __init__(
        self,
        post_repository: PostRepository,
        user_repository: UserRepository,
        reply_repository: ReplyRepository,
        event_publisher: EventPublisher[DomainEvent],
        unit_of_work: UnitOfWork,
    ):
        self._post_repository = post_repository
        self._user_repository = user_repository
        self._reply_repository = reply_repository
        self._event_publisher = event_publisher
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], _Result], context: dict[str, Any]) -> _Result:
        """共通の例外処理を実行"""
        try:
            return operation()
        except ApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except ContentOwnershipException as e:
            # リプライの所有権例外はReplyOwnershipExceptionに変換
            raise ReplyOwnershipException(
                message=str(e), reply_id=e.content_id, user_id=e.user_id, action="delete_reply"
            )
        except SnsDomainException as e:
            raise ApplicationExceptionFactory.create_from_domain_exception(
                e, user_id=context.get("user_id"), reply_id=context.get("reply_id")
            )
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {e!s}", extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {e!s}", original_exception=e)

    def create_reply(self, command: CreateReplyCommand) -> CommandResultDto:
        """リプライを作成（トランザクション境界）"""
        return self._execute_with_error_handling(
            operation=lambda: self._create_reply_impl(command),
            context={
                "action": "create_reply",
                "user_id": command.user_id,
                "parent_post_id": command.parent_post_id,
                "parent_reply_id": command.parent_reply_id,
            },
        )

    def _create_reply_impl(self, command: CreateReplyCommand) -> CommandResultDto:
        """リプライを作成の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # 親ポストまたは親リプライの存在確認と取得
            parent_post = None
            parent_reply = None
            parent_post_id = None
            parent_reply_id = None

            if command.parent_post_id is not None:
                parent_post_id = PostId(command.parent_post_id)
                parent_post = self._post_repository.find_by_id(parent_post_id)
                if parent_post is None:
                    raise ReplyCreationException(
                        f"親ポストが見つかりません: {command.parent_post_id}",
                        command.user_id,
                        parent_post_id=command.parent_post_id,
                    )
            elif command.parent_reply_id is not None:
                parent_reply_id = ReplyId(command.parent_reply_id)
                parent_reply = self._reply_repository.find_by_id(parent_reply_id)
                if parent_reply is None:
                    raise ReplyCreationException(
                        f"親リプライが見つかりません: {command.parent_reply_id}",
                        command.user_id,
                        parent_reply_id=command.parent_reply_id,
                    )
            else:
                raise ReplyCreationException(
                    "親ポストまたは親リプライのどちらかを指定する必要があります", command.user_id
                )

            # PostContentの作成（ハッシュタグはドメイン層で自動抽出）
            reply_content = PostContent.create(command.content, command.visibility)

            # 親コンテンツの作成者を取得
            parent_author_id = None
            if parent_post is not None:
                parent_author_id = parent_post.author_user_id
            elif parent_reply is not None:
                parent_author_id = parent_reply.author_user_id

            mentioned_ids: set[UserId] = set()
            for name in PostContent.extract_mention_display_names(reply_content.content):
                u = self._user_repository.find_by_display_name(name)
                if u is not None:
                    mentioned_ids.add(u.user_id)

            # ReplyAggregateの作成
            reply_id = self._reply_repository.generate_reply_id()
            reply_aggregate = ReplyAggregate.create(
                reply_id,
                parent_post_id,
                parent_reply_id,
                parent_author_id,
                UserId(command.user_id),
                reply_content,
                author_display_name=user_aggregate.profile.display_name,
                mentioned_user_ids=frozenset(mentioned_ids),
                author_identity_token=user_aggregate.identity_token,
                parent_identity_token=parent_post.identity_token
                if parent_post is not None
                else parent_reply.identity_token
                if parent_reply is not None
                else None,
            )

            # リプライを保存
            self._reply_repository.save(reply_aggregate)

            # 親コンテンツにリプライを追加
            if parent_post is not None:
                parent_post.add_reply(reply_id)
                self._post_repository.save(parent_post)
            elif parent_reply is not None:
                parent_reply.add_reply(reply_id)
                self._reply_repository.save(parent_reply)

            self._logger.info(
                f"Reply created successfully: reply_id={reply_id.value}, user_id={command.user_id}, parent_post_id={command.parent_post_id}, parent_reply_id={command.parent_reply_id}"
            )

            return CommandResultDto(
                success=True, message="リプライが正常に作成されました", data={"reply_id": reply_id.value}
            )

    def like_reply(self, command: LikeReplyCommand) -> CommandResultDto:
        """リプライにいいね"""
        return self._execute_with_error_handling(
            operation=lambda: self._like_reply_impl(command),
            context={"action": "like_reply", "user_id": command.user_id, "reply_id": command.reply_id},
        )

    def _like_reply_impl(self, command: LikeReplyCommand) -> CommandResultDto:
        """リプライにいいねの実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # リプライの取得
            reply_aggregate = self._reply_repository.find_by_id(ReplyId(command.reply_id))
            if reply_aggregate is None:
                raise ReplyNotFoundForCommandException(command.reply_id, "like_reply")

            # いいね実行
            provenance = current_execution_provenance()
            reply_aggregate.like_reply(
                UserId(command.user_id),
                liker_display_name=user_aggregate.profile.display_name,
                liker_identity_token=user_aggregate.identity_token,
                execution_provenance=provenance.to_dict() if provenance else None,
            )

            # リプライを保存
            self._reply_repository.save(reply_aggregate)

            self._logger.info(f"Reply liked successfully: reply_id={command.reply_id}, user_id={command.user_id}")

            return CommandResultDto(
                success=True,
                message="リプライにいいねしました",
                data={"reply_id": command.reply_id, "user_id": command.user_id},
            )

    def delete_reply(self, command: DeleteReplyCommand) -> CommandResultDto:
        """リプライを削除"""
        return self._execute_with_error_handling(
            operation=lambda: self._delete_reply_impl(command),
            context={"action": "delete_reply", "user_id": command.user_id, "reply_id": command.reply_id},
        )

    def _delete_reply_impl(self, command: DeleteReplyCommand) -> CommandResultDto:
        """リプライを削除の実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            # ユーザーの存在確認
            user_aggregate = self._user_repository.find_by_id(UserId(command.user_id))
            if user_aggregate is None:
                raise UserNotFoundException(command.user_id, f"ユーザーが見つかりません: {command.user_id}")

            # リプライの取得
            reply_aggregate = self._reply_repository.find_by_id(ReplyId(command.reply_id))
            if reply_aggregate is None:
                raise ReplyNotFoundForCommandException(command.reply_id, "delete_reply")

            # 削除前に親コンテンツを取得（削除後のリプライからは親情報が取得できないため）
            parent_post_id, parent_reply_id = reply_aggregate.get_parent_info()
            parent_post = None
            parent_reply = None

            if parent_post_id is not None:
                parent_post = self._post_repository.find_by_id(parent_post_id)
            elif parent_reply_id is not None:
                parent_reply = self._reply_repository.find_by_id(parent_reply_id)

            # 削除実行（所有権チェックはドメイン層で実施）
            reply_aggregate.delete_reply(UserId(command.user_id))

            # 親コンテンツからリプライを削除
            reply_id_obj = ReplyId(command.reply_id)
            if parent_post is not None:
                parent_post.remove_reply(reply_id_obj)
                self._post_repository.save(parent_post)
            elif parent_reply is not None:
                parent_reply.remove_reply(reply_id_obj)
                self._reply_repository.save(parent_reply)

            # リプライを保存
            self._reply_repository.save(reply_aggregate)

            self._logger.info(f"Reply deleted successfully: reply_id={command.reply_id}, user_id={command.user_id}")

            return CommandResultDto(
                success=True,
                message="リプライが正常に削除されました",
                data={"reply_id": command.reply_id, "user_id": command.user_id},
            )
