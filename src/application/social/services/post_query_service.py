import logging
from datetime import datetime
from typing import List, Optional, Tuple, Callable, Any, TYPE_CHECKING
from functools import wraps

from src.domain.sns.repository import PostRepository, UserRepository
from src.domain.sns.value_object import UserId, PostId
from src.domain.sns.service.post_visibility_domain_service import PostVisibilityDomainService
from src.domain.sns.service.trending_domain_service import TrendingDomainService
from src.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from src.application.social.contracts.dtos import PostDto, ErrorResponseDto
from src.application.social.exceptions import ApplicationException
from src.application.social.exceptions.query.post_query_exception import (
    PostQueryException,
    PostNotFoundException,
    PostAccessDeniedException,
)
from src.application.social.exceptions import ApplicationExceptionFactory
from src.application.social.exceptions import SystemErrorException

if TYPE_CHECKING:
    from src.domain.sns.aggregate.post_aggregate import PostAggregate
    from src.domain.sns.aggregate.user_aggregate import UserAggregate


class PostQueryService:
    """ポスト検索サービス"""

    def __init__(self, post_repository: PostRepository, user_repository: UserRepository):
        self._post_repository = post_repository
        self._user_repository = user_repository
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
                post_id=context.get('post_id')
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

    def _convert_post_to_dto(self, post: "PostAggregate", viewer_user_id: UserId, author_profile_info: dict) -> PostDto:
        """PostAggregateをPostDtoに変換"""
        display_info = post.get_display_info(viewer_user_id)
        return PostDto(
            post_id=display_info["post_id"],
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
            is_replied_by_viewer=display_info["is_replied_by_viewer"],
            mentioned_users=display_info["mentioned_users"],
            is_deleted=display_info["is_deleted"]
        )

    def _filter_and_convert_posts(
        self,
        posts: List["PostAggregate"],
        viewer_user: "UserAggregate",
        viewer_id: UserId,
        author_user_map: Optional[dict] = None
    ) -> List[PostDto]:
        """ポストの権限チェックとDTO変換を行う共通メソッド"""
        result = []

        # 著者情報を取得するためのマップを作成
        if author_user_map is None:
            author_user_map = {}
            unique_author_ids = set(post.author_user_id for post in posts)
            author_users = self._user_repository.find_users_by_ids(list(unique_author_ids))
            for author_user in author_users:
                author_user_map[author_user.user_id] = author_user

        # 著者プロフィール情報を取得するためのマップを作成
        author_profile_cache = {}
        for author_user_id, author_user in author_user_map.items():
            author_profile_cache[author_user_id] = author_user.get_user_profile_info()

        for post in posts:
            author_user_id = post.author_user_id
            author_user = author_user_map.get(author_user_id)

            if author_user is None:
                continue

            # 権限チェック（ドメインサービスを使用）
            if PostVisibilityDomainService.can_view_post(post, viewer_user, author_user):
                author_profile_info = author_profile_cache[author_user_id]
                dto = self._convert_post_to_dto(post, viewer_id, author_profile_info)
                result.append(dto)

        return result

    def get_user_timeline(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ユーザーのポスト一覧を取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_user_timeline_impl(user_id, viewer_user_id, limit, offset),
            context={
                "action": "get_user_timeline",
                "user_id": user_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_user_timeline_impl(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ユーザーのポスト一覧を取得の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        target_user_id = UserId(user_id)
        viewer_id = UserId(viewer_user_id)

        # 閲覧者と対象ユーザーの情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        target_user = self._user_repository.find_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundException(user_id, f"ユーザーが見つかりません: {user_id}")

        # 対象ユーザーのポストを取得
        posts = self._post_repository.find_by_user_id(target_user_id, limit=limit, offset=offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        author_user_map = {target_user.user_id: target_user}
        return self._filter_and_convert_posts(posts, viewer_user, viewer_id, author_user_map)

    def get_home_timeline(self, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """フォロー中のユーザーのポスト一覧を取得（ブロック・可視性フィルタ適用）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_home_timeline_impl(viewer_user_id, limit, offset),
            context={
                "action": "get_home_timeline",
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_home_timeline_impl(self, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """フォロー中のユーザーのポスト一覧を取得の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        viewer_id = UserId(viewer_user_id)

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # フォロー中のユーザーのIDを取得
        followee_ids = self._user_repository.find_followees(viewer_id)

        # フォロー中のユーザーがいない場合は空のリストを返す
        if not followee_ids:
            return []

        # フォロー中ユーザーのポストを取得（新しい順、offset+limitで取得）
        posts = self._post_repository.find_by_user_ids(followee_ids, limit=limit + offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_posts(posts, viewer_user, viewer_id)

        # 作成日時でソート（新しい順）
        result.sort(key=lambda x: x.get_sort_key_by_created_at(), reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    def search_posts_by_keyword(self, keyword: str, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """キーワードでポストを検索（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._search_posts_by_keyword_impl(keyword, viewer_user_id, limit, offset),
            context={
                "action": "search_posts_by_keyword",
                "viewer_user_id": viewer_user_id
            }
        )

    def _search_posts_by_keyword_impl(self, keyword: str, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """キーワードでポストを検索の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        viewer_id = UserId(viewer_user_id)

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # キーワードでポストを検索
        keyword_posts = self._post_repository.search_posts_by_content(keyword.strip(), limit=limit + offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_posts(keyword_posts, viewer_user, viewer_id)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    def get_popular_posts(self, viewer_user_id: int, timeframe_hours: int = 24, limit: int = 10, offset: int = 0) -> List[PostDto]:
        """人気ポストランキングを取得（いいね数順、権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_popular_posts_impl(viewer_user_id, timeframe_hours, limit, offset),
            context={
                "action": "get_popular_posts",
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_popular_posts_impl(self, viewer_user_id: int, timeframe_hours: int = 24, limit: int = 10, offset: int = 0) -> List[PostDto]:
        """人気ポストランキングを取得の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        viewer_id = UserId(viewer_user_id)

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # 人気ポストを取得（いいね数順）
        popular_posts = self._post_repository.find_trending_posts(timeframe_hours=timeframe_hours, limit=limit + offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_posts(popular_posts, viewer_user, viewer_id)

        # offsetとlimitを適用（既にいいね数順にソートされているはず）
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    def get_post(self, post_id: int, viewer_user_id: int) -> Optional[PostDto]:
        """個別のポストを取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_post_impl(post_id, viewer_user_id),
            context={
                "action": "get_post",
                "post_id": post_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_post_impl(self, post_id: int, viewer_user_id: int) -> Optional[PostDto]:
        """個別のポストを取得の実装"""
        # オブジェクトを作成（ドメイン層でバリデーション）
        target_post_id = PostId(post_id)
        viewer_id = UserId(viewer_user_id)

        # ポストを取得
        post = self._post_repository.find_by_id(post_id)
        if post is None:
            raise PostNotFoundException(post_id)

        # 閲覧者と著者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        author_user = self._user_repository.find_by_id(post.author_user_id)
        if author_user is None:
            # 著者が見つからない場合はアクセス拒否
            raise PostAccessDeniedException(post_id, viewer_user_id)

        # 閲覧権限チェック（ドメインサービスを使用）
        if not PostVisibilityDomainService.can_view_post(post, viewer_user, author_user):
            raise PostAccessDeniedException(post_id, viewer_user_id)

        # 著者プロフィール情報を取得
        author_profile_info = self._get_user_profile_info(post.author_user_id)

        # DTOに変換して返却
        return self._convert_post_to_dto(post, viewer_id, author_profile_info)

    def get_private_posts(self, user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """自分のプライベートポストのみを取得（メモ機能）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_private_posts_impl(user_id, limit, offset),
            context={
                "action": "get_private_posts",
                "user_id": user_id
            }
        )

    def _get_private_posts_impl(self, user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """自分のプライベートポストのみを取得の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        owner_id = UserId(user_id)

        # ユーザーの存在確認
        owner_user = self._user_repository.find_by_id(owner_id)
        if owner_user is None:
            raise UserNotFoundException(user_id, f"ユーザーが見つかりません: {user_id}")

        # リポジトリからプライベートポストを取得（ドメイン層のロジックを使用）
        private_posts = self._post_repository.find_private_posts_by_user(owner_id, limit=limit, offset=offset)

        # DTOに変換
        result = []
        author_profile_info = self._get_user_profile_info(owner_id)  # 自分のプロフィール

        for post in private_posts:
            dto = self._convert_post_to_dto(post, owner_id, author_profile_info)
            result.append(dto)

        return result

    def get_liked_posts(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ユーザーがいいねしたポスト一覧を取得（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_liked_posts_impl(user_id, viewer_user_id, limit, offset),
            context={
                "action": "get_liked_posts",
                "user_id": user_id,
                "viewer_user_id": viewer_user_id
            }
        )

    def _get_liked_posts_impl(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ユーザーがいいねしたポスト一覧を取得の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        target_user_id = UserId(user_id)
        viewer_id = UserId(viewer_user_id)

        # 閲覧者と対象ユーザーの情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        target_user = self._user_repository.find_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundException(user_id, f"ユーザーが見つかりません: {user_id}")

        # 対象ユーザーがいいねしたポストを取得
        liked_posts = self._post_repository.find_liked_posts_by_user(target_user_id, limit=limit + offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_posts(liked_posts, viewer_user, viewer_id)

        # offsetとlimitを適用（いいねした順にソートされているはず）
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    def search_posts_by_hashtag(self, hashtag: str, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ハッシュタグでポストを検索（権限チェック付き）"""
        return self._execute_with_error_handling(
            operation=lambda: self._search_posts_by_hashtag_impl(hashtag, viewer_user_id, limit, offset),
            context={
                "action": "search_posts_by_hashtag",
                "viewer_user_id": viewer_user_id
            }
        )

    def _search_posts_by_hashtag_impl(self, hashtag: str, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ハッシュタグでポストを検索の実装"""
        # UserIdオブジェクトを作成（ドメイン層でバリデーション）
        viewer_id = UserId(viewer_user_id)

        # 閲覧者の情報を取得
        viewer_user = self._user_repository.find_by_id(viewer_id)
        if viewer_user is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        # ハッシュタグでポストを検索
        hashtag_posts = self._post_repository.find_posts_by_hashtag(hashtag.strip(), limit=limit + offset)

        # 権限チェックとDTO変換（共通メソッドを使用）
        result = self._filter_and_convert_posts(hashtag_posts, viewer_user, viewer_id)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    def get_trending_hashtags(self, limit: int = 10, decay_lambda: float = 0.1, recent_window_hours: float = 1.0) -> List[str]:
        """トレンドハッシュタグを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_trending_hashtags_impl(limit, decay_lambda, recent_window_hours),
            context={
                "action": "get_trending_hashtags"
            }
        )

    def _get_trending_hashtags_impl(self, limit: int = 10, decay_lambda: float = 0.1, recent_window_hours: float = 1.0) -> List[str]:
        """トレンドハッシュタグを取得の実装"""
        # 過去24時間のポストを取得（全ポストを使用）
        recent_posts = self._post_repository.find_posts_in_timeframe(timeframe_hours=24)

        # トレンドハッシュタグを計算（権限チェックなし）
        now = datetime.now()
        trending_hashtags = TrendingDomainService.calculate_trending_hashtags(
            posts=recent_posts,
            now=now,
            decay_lambda=decay_lambda,
            recent_window_hours=recent_window_hours,
            max_results=limit
        )

        # ハッシュタグのみを返す（#付き）
        return [f"#{hashtag}" for hashtag, score in trending_hashtags]
