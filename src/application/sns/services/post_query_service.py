import logging
from typing import List, Optional, Tuple, Callable, TYPE_CHECKING
from functools import wraps

from src.domain.sns.repository import PostRepository, UserRepository
from src.domain.sns.value_object import UserId, PostId
from src.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from src.application.sns.contracts.dtos import PostDto, ErrorResponseDto
from src.application.sns.exceptions import ApplicationException
from src.application.sns.exceptions.query.post_query_exception import (
    PostQueryException,
    PostNotFoundException,
    PostAccessDeniedException,
    InvalidPostIdException,
)
from src.application.sns.exceptions import ApplicationExceptionFactory
from src.application.sns.exceptions import SystemErrorException

if TYPE_CHECKING:
    from src.domain.sns.aggregate.post_aggregate import PostAggregate


class PostQueryService:
    """ポスト検索サービス"""

    def __init__(self, post_repository: PostRepository, user_repository: UserRepository):
        self._post_repository = post_repository
        self._user_repository = user_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _handle_domain_exception(self, exception: SnsDomainException, post_id: Optional[int] = None, user_id: Optional[int] = None, viewer_user_id: Optional[int] = None) -> ErrorResponseDto:
        """ドメイン例外を適切なエラーレスポンスに変換"""
        # デフォルトのエラーコードとメッセージを取得
        error_code, message = self._get_error_info_from_exception(exception)

        # ログに記録
        self._logger.warning(
            f"ドメイン例外が発生: {error_code} - {message}",
            extra={
                "error_type": type(exception).__name__,
                "post_id": post_id,
                "user_id": user_id,
                "viewer_user_id": viewer_user_id,
                "exception_message": str(exception),
            }
        )

        return ErrorResponseDto(
            error_code=error_code,
            message=message,
            details=str(exception),
            user_id=user_id,
            target_user_id=viewer_user_id,
        )

    def _get_error_info_from_exception(self, exception: SnsDomainException) -> tuple[str, str]:
        """例外の種類に基づいてエラーコードとメッセージを取得"""
        # Exceptionクラスに定義されたエラーコードを使用
        error_code = getattr(exception, 'error_code', 'UNKNOWN_ERROR')
        message = str(exception)

        return error_code, message

    def _convert_to_application_exception(self, domain_exception: SnsDomainException, post_id: Optional[int] = None, user_id: Optional[int] = None, viewer_user_id: Optional[int] = None) -> PostQueryException:
        """ドメイン例外をアプリケーション例外に変換（簡素化）"""
        return ApplicationExceptionFactory.create_from_domain_exception(
            domain_exception,
            post_id=post_id,
            user_id=user_id,
            target_user_id=viewer_user_id
        )

    def _get_user_ids_from_params(self, *args, **kwargs) -> Tuple[Optional[int], Optional[int]]:
        """パラメータからユーザーIDを取得"""
        user_id = None
        viewer_user_id = None

        # 引数を確認
        for arg in args:
            if isinstance(arg, int):
                if user_id is None:
                    user_id = arg
                elif viewer_user_id is None:
                    viewer_user_id = arg
                else:
                    break  # 2つ以上見つかったら終了

        # kwargsを確認
        if 'viewer_user_id' in kwargs:
            viewer_user_id = kwargs['viewer_user_id']
        if 'user_id' in kwargs:
            user_id = kwargs['user_id']

        return user_id, viewer_user_id

    @staticmethod
    def handle_domain_exceptions(method: Callable) -> Callable:
        """ドメイン例外を処理するデコレータ"""
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except ApplicationException as e:
                # アプリケーション例外はそのまま再スロー
                raise e
            except SnsDomainException as e:
                user_id, viewer_user_id = self._get_user_ids_from_params(*args, **kwargs)
                post_id = kwargs.get('post_id')
                app_exception = self._convert_to_application_exception(e, post_id=post_id, user_id=user_id, viewer_user_id=viewer_user_id)
                error_response = self._handle_domain_exception(e, post_id=post_id, user_id=user_id, viewer_user_id=viewer_user_id)
                self._logger.error(f"{method.__name__} failed: {error_response.message}", extra={"error": error_response})
                raise app_exception
            except Exception as e:
                user_id, viewer_user_id = self._get_user_ids_from_params(*args, **kwargs)
                post_id = kwargs.get('post_id')
                self._logger.error(f"Unexpected error in {method.__name__}: {str(e)}", extra={
                    "post_id": post_id,
                    "user_id": user_id,
                    "viewer_user_id": viewer_user_id,
                    "action": method.__name__
                })
                raise SystemErrorException(f"{method.__name__} failed: {str(e)}", original_exception=e)
        return wrapper

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

    @handle_domain_exceptions
    def get_user_timeline(self, user_id: int, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """ユーザーのポスト一覧を取得（権限チェック付き）"""
        # パラメータバリデーション
        if user_id <= 0:
            raise InvalidPostIdException(user_id)  # ポストIDの例外を流用
        if viewer_user_id <= 0:
            raise InvalidPostIdException(viewer_user_id)

        # UserIdオブジェクトを作成
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

        # 閲覧権限チェックとDTO変換
        result = []
        author_profile_info = self._get_user_profile_info(target_user_id)  # キャッシュ用

        for post in posts:
            # 閲覧権限チェック
            if post.can_be_viewed_by(viewer_user, target_user):
                dto = self._convert_post_to_dto(post, viewer_id, author_profile_info)
                result.append(dto)

        return result

    @handle_domain_exceptions
    def get_home_timeline(self, viewer_user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """フォロー中のユーザーのポスト一覧を取得（ブロック・可視性フィルタ適用）"""
        # パラメータバリデーション
        if viewer_user_id <= 0:
            raise InvalidPostIdException(viewer_user_id)

        # UserIdオブジェクトを作成
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

        # フォロー中ユーザーのポストを取得（新しい順）
        posts = self._post_repository.find_by_user_ids(followee_ids, limit=limit)

        # 閲覧権限チェックとDTO変換
        result = []
        author_profile_cache = {}  # 著者プロフィール情報をキャッシュ

        for post in posts:
            author_user_id = post.author_user_id

            # 著者ユーザーの情報を取得（キャッシュ）
            if author_user_id not in author_profile_cache:
                try:
                    author_profile_cache[author_user_id] = self._get_user_profile_info(author_user_id)
                except UserNotFoundException:
                    # 著者が見つからない場合はスキップ
                    continue

            author_profile_info = author_profile_cache[author_user_id]

            # 著者ユーザーの集約を取得
            author_user = self._user_repository.find_by_id(author_user_id)
            if author_user is None:
                continue

            # 閲覧権限チェック
            if post.can_be_viewed_by(viewer_user, author_user):
                dto = self._convert_post_to_dto(post, viewer_id, author_profile_info)
                result.append(dto)

        # 作成日時でソート（新しい順）- リポジトリがソート済みの場合もあるが念のため
        result.sort(key=lambda x: x.created_at, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        if len(result) > limit:
            result = result[:limit]

        return result

    @handle_domain_exceptions
    def get_post(self, post_id: int, viewer_user_id: int) -> Optional[PostDto]:
        """個別のポストを取得（権限チェック付き）"""
        # パラメータバリデーション
        if post_id <= 0:
            raise InvalidPostIdException(post_id)
        if viewer_user_id <= 0:
            raise InvalidPostIdException(viewer_user_id)

        # オブジェクトを作成
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

        # 閲覧権限チェック
        if not post.can_be_viewed_by(viewer_user, author_user):
            raise PostAccessDeniedException(post_id, viewer_user_id)

        # 著者プロフィール情報を取得
        author_profile_info = self._get_user_profile_info(post.author_user_id)

        # DTOに変換して返却
        return self._convert_post_to_dto(post, viewer_id, author_profile_info)

    @handle_domain_exceptions
    def get_private_posts(self, user_id: int, limit: int = 20, offset: int = 0) -> List[PostDto]:
        """自分のプライベートポストのみを取得（メモ機能）"""
        # パラメータバリデーション
        if user_id <= 0:
            raise InvalidPostIdException(user_id)

        # UserIdオブジェクトを作成
        owner_id = UserId(user_id)

        # ユーザーの存在確認
        owner_user = self._user_repository.find_by_id(owner_id)
        if owner_user is None:
            raise UserNotFoundException(user_id, f"ユーザーが見つかりません: {user_id}")

        # プライベートポストを取得
        # PostRepositoryにプライベートポストを取得する専用メソッドがないため、
        # ページングしながら全ポストを取得してプライベートポストのみをフィルタリング
        private_posts = []
        page_size = 100  # 1ページあたりの取得件数
        current_offset = 0

        # 全てのポストを取得するまでページング
        while True:
            page_posts = self._post_repository.find_by_user_id(owner_id, limit=page_size, offset=current_offset)
            if not page_posts:
                break  # これ以上ポストがない

            # このページ内のプライベートポストを抽出
            page_private_posts = [
                post for post in page_posts
                if post.post_content.visibility.value == "private"
            ]
            private_posts.extend(page_private_posts)

            current_offset += page_size

            # 十分なプライベートポストが集まったら終了（パフォーマンス最適化）
            if len(private_posts) >= offset + limit * 2:  # 余裕を持って取得
                break

        # 作成日時でソート（新しい順）
        private_posts.sort(key=lambda x: x.created_at, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            private_posts = private_posts[offset:]
        if len(private_posts) > limit:
            private_posts = private_posts[:limit]

        # DTOに変換
        result = []
        author_profile_info = self._get_user_profile_info(owner_id)  # 自分のプロフィール

        for post in private_posts:
            dto = self._convert_post_to_dto(post, owner_id, author_profile_info)
            result.append(dto)

        return result
