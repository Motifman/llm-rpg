from abc import abstractmethod
from typing import List, Optional, Dict
from src.domain.common.repository import Repository
from src.domain.sns.aggregate import PostAggregate
from src.domain.sns.value_object import Mention, PostId, ReplyId, UserId


class PostRepository(Repository[PostAggregate]):
    """PostAggregateのリポジトリインターフェース"""

    @abstractmethod
    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """特定のユーザーのポスト一覧を取得（タイムライン用）"""
        pass

    @abstractmethod
    def find_by_user_ids(self, user_ids: List[UserId], limit: int = 50) -> List[PostAggregate]:
        """複数のユーザーのポストを取得（フォロー中ユーザーの投稿取得用）"""
        pass

    @abstractmethod
    def find_recent_posts(self, limit: int = 20) -> List[PostAggregate]:
        """最新のポストを取得（トレンド表示用）"""
        pass

    @abstractmethod
    def find_posts_mentioning_user(self, user_name: str, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーをメンションしたポストを取得"""
        pass

    @abstractmethod
    def find_liked_posts_by_user(self, user_id: UserId, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーがいいねしたポスト一覧を取得"""
        pass

    @abstractmethod
    def find_posts_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーからいいねされたポスト一覧を取得"""
        pass

    @abstractmethod
    def search_posts_by_content(self, query: str, limit: int = 20) -> List[PostAggregate]:
        """コンテンツでポストを検索"""
        pass

    @abstractmethod
    def get_like_count(self, post_id: PostId) -> int:
        """特定のポストのいいね数を取得"""
        pass

    @abstractmethod
    def find_posts_with_replies(self, post_ids: List[PostId]) -> Dict[PostId, List[ReplyId]]:
        """複数のポストとそれらのリプライID一覧を取得"""
        pass

    @abstractmethod
    def find_posts_excluding_blocked_users(
        self,
        user_id: UserId,
        blocked_user_ids: List[UserId],
        limit: int = 20
    ) -> List[PostAggregate]:
        """ブロックしたユーザーのポストを除外した一覧を取得"""
        pass

    @abstractmethod
    def get_user_post_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの投稿統計（総投稿数、総いいね数など）を取得"""
        pass

    @abstractmethod
    def find_trending_posts(self, timeframe_hours: int = 24, limit: int = 10) -> List[PostAggregate]:
        """トレンドのポストを取得（いいね数やリプライ数でソート）"""
        pass

    @abstractmethod
    def bulk_delete_posts(self, post_ids: List[PostId], user_id: UserId) -> int:
        """複数のポストを一括削除（自分のポストのみ）"""
        pass

    @abstractmethod
    def cleanup_deleted_posts(self, older_than_days: int = 30) -> int:
        """古い削除済みポストをクリーンアップ"""
        pass
