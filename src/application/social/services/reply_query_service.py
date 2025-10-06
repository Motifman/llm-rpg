import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Callable, Any, TYPE_CHECKING
from functools import wraps

from src.domain.sns.repository import PostRepository, UserRepository, ReplyRepository
from src.domain.sns.value_object import UserId, PostId, ReplyId
from src.domain.sns.service.post_visibility_domain_service import PostVisibilityDomainService
from src.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from src.application.social.contracts.dtos import ReplyDto, ReplyThreadDto, PostDto, ErrorResponseDto
from src.application.social.exceptions import ApplicationException
from src.application.social.exceptions.query.reply_query_exception import (
    ReplyQueryException,
    ReplyNotFoundException,
    ReplyAccessDeniedException,
)
from src.application.social.exceptions import ApplicationExceptionFactory
from src.application.social.exceptions import SystemErrorException

if TYPE_CHECKING:
    from src.domain.sns.aggregate.post_aggregate import PostAggregate
    from src.domain.sns.aggregate.reply_aggregate import ReplyAggregate
    from src.domain.sns.aggregate.user_aggregate import UserAggregate


class ReplyQueryService:
    """リプライ検索サービス"""

    def __init__(self, post_repository: PostRepository, user_repository: UserRepository, reply_repository: ReplyRepository):
        self._post_repository = post_repository
        self._user_repository = user_repository
        self._reply_repository = reply_repository
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
                target_user_id=context.get('viewer_user_id'),
                post_id=context.get('post_id'),
                reply_id=context.get('reply_id')
            )
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def _get_user_profile_info(self, user_id: UserId) -> dict:
        """ユーザーのプロフィール情報を取得"""
        user_aggregate = self._user_repository.find_by_id(user_id)
        if user_aggregate is None:
            raise UserNotFoundException(user_id.value, f"ユーザーが見つかりません: {user_id.value}")
        return user_aggregate.get_user_profile_info()

    def _create_deleted_post_dto(self, post: "PostAggregate", viewer_user: "UserAggregate") -> PostDto:
        """削除されたポストのDTOを作成"""
        return PostDto(
            post_id=post.post_id.value,
            author_user_id=post.author_user_id.value,
            author_user_name="[削除済み]",  # 削除されたので情報非表示
            author_display_name="[削除済み]",
            content="",  # 空にする
            hashtags=[],
            visibility="deleted",
            created_at=post.created_at,
            like_count=0,  # 削除されたので0
            reply_count=post.get_reply_count(),  # リプライ数は保持
            is_liked_by_viewer=False,
            is_replied_by_viewer=False,
            mentioned_users=[],
            is_deleted=True,
            deletion_message="このポストは削除されています"
        )

    def _convert_reply_to_dto(self, reply: "ReplyAggregate", viewer_user_id: UserId, author_profile_info: dict, depth: int = 0) -> ReplyDto:
        """ReplyAggregateをReplyDtoに変換（削除リプライ対応）"""
        display_info = reply.get_display_info(viewer_user_id)

        if reply.deleted:
            # 削除されたリプライの場合
            return ReplyDto(
                reply_id=display_info["reply_id"],
                parent_post_id=display_info["parent_post_id"],
                parent_reply_id=display_info["parent_reply_id"],
                author_user_id=display_info["author_user_id"],
                author_user_name="[削除済み]",
                author_display_name="[削除済み]",
                content="",
                hashtags=[],
                visibility="deleted",
                created_at=display_info["created_at"],
                like_count=0,
                reply_count=display_info["reply_count"],  # 子リプライ数は保持
                is_liked_by_viewer=False,
                mentioned_users=[],
                is_deleted=True,
                deletion_message="このリプライは削除されています",
                depth=depth,
                has_replies=display_info["has_replies"]
            )
        else:
            # 通常のリプライ
            return ReplyDto(
                reply_id=display_info["reply_id"],
                parent_post_id=display_info["parent_post_id"],
                parent_reply_id=display_info["parent_reply_id"],
                author_user_id=display_info["author_user_id"],
                author_user_name=author_profile_info["user_name"],
                author_display_name=author_profile_info["display_name"],
                content=display_info["content"],
                hashtags=display_info["hashtags"],
                visibility=display_info["visibility"],
                created_at=display_info["created_at"],
                like_count=display_info["like_count"],
                reply_count=display_info["reply_count"],
                is_liked_by_viewer=display_info["is_liked_by_viewer"],
                mentioned_users=display_info["mentioned_users"],
                is_deleted=display_info["is_deleted"],
                depth=depth,
                has_replies=display_info["has_replies"],
            )

    def _filter_and_convert_replies(
        self,
        replies: List["ReplyAggregate"],
        viewer_user: "UserAggregate",
        viewer_id: UserId,
        author_user_map: Optional[dict] = None
    ) -> List[ReplyDto]:
        """リプライの権限チェックとDTO変換を行う共通メソッド"""
        result = []

        # 著者情報を取得するためのマップを作成
        if author_user_map is None:
            author_user_map = {}
            unique_author_ids = set(reply.author_user_id for reply in replies)
            author_users = self._user_repository.find_users_by_ids(list(unique_author_ids))
            for author_user in author_users:
                author_user_map[author_user.user_id] = author_user

        # 著者プロフィール情報を取得するためのマップを作成
        author_profile_cache = {}
        for author_user_id, author_user in author_user_map.items():
            author_profile_cache[author_user_id] = author_user.get_user_profile_info()

        for reply in replies:
            author_user_id = reply.author_user_id
            author_user = author_user_map.get(author_user_id)

            if author_user is None:
                continue

            # 権限チェック（削除リプライも特別に許可）
            can_view_reply = (not reply.deleted and PostVisibilityDomainService.can_view_reply(reply, viewer_user, author_user)) or \
                           (reply.deleted and PostVisibilityDomainService.can_view_deleted_reply_for_thread(reply, viewer_user, author_user))

            if can_view_reply:
                author_profile_info = author_profile_cache[author_user_id]
                dto = self._convert_reply_to_dto(reply, viewer_id, author_profile_info)
                result.append(dto)

        return result

    def get_replies_by_post_id(self, post_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[ReplyDto]:
        """ポストへのリプライ一覧を取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_replies_by_post_id_impl(post_id, viewer_user_id, limit, offset),
            context={
                "action": "get_replies_by_post_id",
                "post_id": post_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_replies_by_post_id_impl(self, post_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[ReplyDto]:
        """ポストへのリプライ一覧を取得の実装"""
        # オブジェクトを作成（ドメイン層でバリデーション）
        target_post_id = PostId(post_id)
        viewer_id = UserId(viewer_user_id)

        # 閲覧者と対象ポストの情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # 対象ポストが存在するか確認
        target_post = self._post_repository.find_by_id(target_post_id)
        if target_post is None:
            raise ReplyNotFoundException(post_id, "ポストが見つかりません")

        # リプライを取得（削除済みを含む）
        replies = self._reply_repository.find_by_post_id_include_deleted(target_post_id, limit=limit, offset=offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_replies(replies, viewer_user, viewer_id)

        # 作成日時でソート（古い順）
        result.sort(key=lambda x: x.get_sort_key_by_created_at())

        return result

    def get_reply_thread(self, post_id: int, viewer_user_id: int, max_depth: int = 3) -> ReplyThreadDto:
        """ポストとそのリプライのツリー構造を取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_reply_thread_impl(post_id, viewer_user_id, max_depth),
            context={
                "action": "get_reply_thread",
                "post_id": post_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_reply_thread_impl(self, post_id: int, viewer_user_id: int, max_depth: int = 3) -> ReplyThreadDto:
        """ポストとそのリプライのツリー構造を取得の実装"""
        # オブジェクトを作成（ドメイン層でバリデーション）
        target_post_id = PostId(post_id)
        viewer_id = UserId(viewer_user_id)

        # ポストを取得
        post = self._post_repository.find_by_id(target_post_id)
        if post is None:
            raise ReplyNotFoundException(post_id, "ポストが見つかりません")

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # ポストの著者情報を取得
        post_author_user = self._user_repository.find_by_id(post.author_user_id)
        if post_author_user is None:
            raise ReplyAccessDeniedException(post_id, viewer_user_id, "ポストの著者が見つかりません")

        # ポストの閲覧権限チェック（削除されている場合も特別に許可）
        can_view_post = (not post.deleted and PostVisibilityDomainService.can_view_post(post, viewer_user, post_author_user)) or \
                       (post.deleted and PostVisibilityDomainService.can_view_deleted_post_for_reply_thread(post, viewer_user, post_author_user))

        if not can_view_post:
            raise ReplyAccessDeniedException(post_id, viewer_user_id, "ポストの閲覧権限がありません")

        # ポストのDTO変換（削除されている場合は特別処理）
        if post.deleted:
            post_dto = self._create_deleted_post_dto(post, viewer_user)
        else:
            post_author_profile_info = self._get_user_profile_info(post.author_user_id)
            post_dto = PostDto(
                post_id=post.post_id.value,
                author_user_id=post.author_user_id.value,
                author_user_name=post_author_profile_info["user_name"],
                author_display_name=post_author_profile_info["display_name"],
                content=post.post_content.content,
                hashtags=list(post.post_content.hashtags),
                visibility=post.post_content.visibility.value,
                created_at=post.created_at,
                like_count=post.get_like_count(),
                reply_count=post.get_reply_count(),
                is_liked_by_viewer=post.is_liked_by_user(viewer_id),
                is_replied_by_viewer=False,  # ポストには直接リプライできない
                mentioned_users=list(post.mentioned_users()),
                is_deleted=post.deleted
            )

        # リプライツリーを取得（削除済みを含む）
        reply_tree = self._reply_repository.find_thread_replies_include_deleted(target_post_id, max_depth=max_depth)

        # リプライをフラットなリストに変換（ツリー構造はdepthで表現）
        reply_dtos = self._convert_reply_tree_to_flat_list(reply_tree, viewer_user, viewer_id)

        return ReplyThreadDto(post=post_dto, replies=reply_dtos)

    def _convert_reply_tree_to_flat_list(
        self,
        reply_tree: Dict[Any, List["ReplyAggregate"]],
        viewer_user: "UserAggregate",
        viewer_id: UserId,
        current_depth: int = 0
    ) -> List[ReplyDto]:
        """リプライツリーをフラットなDTOリストに変換"""
        result = []

        # 著者情報を取得するためのマップを作成
        all_replies = []
        for replies in reply_tree.values():
            all_replies.extend(replies)

        if not all_replies:
            return result

        author_user_map = {}
        unique_author_ids = set(reply.author_user_id for reply in all_replies)
        author_users = self._user_repository.find_users_by_ids(list(unique_author_ids))
        for author_user in author_users:
            author_user_map[author_user.user_id] = author_user

        # 著者プロフィール情報を取得するためのマップを作成
        author_profile_cache = {}
        for author_user_id, author_user in author_user_map.items():
            author_profile_cache[author_user_id] = author_user.get_user_profile_info()

        # ツリーを再帰的に処理
        def process_replies(parent_id: Any, depth: int):
            if depth > 3:  # 最大深度制限
                return

            replies = reply_tree.get(parent_id, [])
            for reply in replies:
                author_user = author_user_map.get(reply.author_user_id)
                if author_user is None:
                    continue

                # 権限チェック（削除リプライも特別に許可）
                can_view_reply = (not reply.deleted and PostVisibilityDomainService.can_view_reply(reply, viewer_user, author_user)) or \
                               (reply.deleted and PostVisibilityDomainService.can_view_deleted_reply_for_thread(reply, viewer_user, author_user))

                if can_view_reply:
                    author_profile_info = author_profile_cache[reply.author_user_id]
                    dto = self._convert_reply_to_dto(reply, viewer_id, author_profile_info, depth)
                    result.append(dto)

                    # 子リプライを処理
                    process_replies(reply.reply_id, depth + 1)

        # ルートレベルのリプライから開始
        from src.domain.sns.value_object import PostId
        root_post_id = next((k for k in reply_tree.keys() if isinstance(k, PostId)), None)
        if root_post_id:
            process_replies(root_post_id, 0)

        return result

    def get_reply_by_id(self, reply_id: int, viewer_user_id: int) -> Optional[ReplyDto]:
        """個別のリプライを取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_reply_by_id_impl(reply_id, viewer_user_id),
            context={
                "action": "get_reply_by_id",
                "reply_id": reply_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_reply_by_id_impl(self, reply_id: int, viewer_user_id: int) -> Optional[ReplyDto]:
        """個別のリプライを取得の実装"""
        # オブジェクトを作成（ドメイン層でバリデーション）
        target_reply_id = ReplyId(reply_id)
        viewer_id = UserId(viewer_user_id)

        # リプライを取得
        reply = self._reply_repository.find_by_id(target_reply_id)
        if reply is None:
            raise ReplyNotFoundException(reply_id)

        # 閲覧者と著者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        author_user = self._user_repository.find_by_id(reply.author_user_id)
        if author_user is None:
            # 著者が見つからない場合はアクセス拒否
            raise ReplyAccessDeniedException(reply_id, viewer_user_id)

        # 閲覧権限チェック（ドメインサービスを使用）
        if not PostVisibilityDomainService.can_view_reply(reply, viewer_user, author_user):
            raise ReplyAccessDeniedException(reply_id, viewer_user_id)

        # 著者プロフィール情報を取得
        author_profile_info = self._get_user_profile_info(reply.author_user_id)

        # DTOに変換して返却
        return self._convert_reply_to_dto(reply, viewer_id, author_profile_info)

    def get_user_replies(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[ReplyDto]:
        """ユーザーのリプライ一覧を取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_user_replies_impl(user_id, viewer_user_id, limit, offset),
            context={
                "action": "get_user_replies",
                "user_id": user_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_user_replies_impl(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[ReplyDto]:
        """ユーザーのリプライ一覧を取得の実装"""
        # オブジェクトを作成（ドメイン層でバリデーション）
        target_user_id = UserId(user_id)
        viewer_id = UserId(viewer_user_id)

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # リプライを取得
        replies = self._reply_repository.find_by_user_id(target_user_id, limit=limit, offset=offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_replies(replies, viewer_user, viewer_id)

        # 作成日時でソート（新しい順）
        result.sort(key=lambda x: x.get_sort_key_by_created_at(), reverse=True)

        return result
