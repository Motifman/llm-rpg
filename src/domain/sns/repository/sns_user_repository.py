from abc import abstractmethod
from typing import List, Optional, Dict, Tuple
from src.domain.common.repository import Repository
from src.domain.sns.aggregate import UserAggregate
from src.domain.sns.value_object import UserId


class UserRepository(Repository[UserAggregate, UserId]):
    """UserAggregateのリポジトリインターフェース"""

    @abstractmethod
    def find_by_user_name(self, user_name: str) -> Optional[UserAggregate]:
        """ユーザー名でユーザーを検索"""
        pass

    @abstractmethod
    def find_by_display_name(self, display_name: str) -> Optional[UserAggregate]:
        """表示名でユーザーを検索"""
        pass

    @abstractmethod
    def find_followers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーのフォロワー一覧を取得"""
        pass

    @abstractmethod
    def find_followees(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがフォローしているユーザー一覧を取得"""
        pass

    @abstractmethod
    def find_mutual_follows(self, user_id: UserId) -> List[UserId]:
        """相互フォロー関係を取得"""
        pass

    @abstractmethod
    def count_followers(self, user_id: UserId) -> int:
        """フォロワー数を取得"""
        pass

    @abstractmethod
    def count_followees(self, user_id: UserId) -> int:
        """フォロー数を取得"""
        pass

    @abstractmethod
    def find_blocked_users(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがブロックしているユーザー一覧を取得"""
        pass

    @abstractmethod
    def find_blockers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーをブロックしているユーザー一覧を取得"""
        pass

    @abstractmethod
    def is_blocked(self, blocker_user_id: UserId, blocked_user_id: UserId) -> bool:
        """ブロック関係の確認"""
        pass

    @abstractmethod
    def find_subscribers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーをサブスクライブしているユーザー一覧を取得"""
        pass

    @abstractmethod
    def find_subscriptions(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがサブスクライブしているユーザー一覧を取得"""
        pass

    @abstractmethod
    def is_subscribed(self, subscriber_user_id: UserId, subscribed_user_id: UserId) -> bool:
        """サブスクライブ関係の確認"""
        pass

    @abstractmethod
    def update_profile(self, user_id: UserId, bio: str, display_name: str) -> UserAggregate:
        """ユーザープロフィールを更新"""
        pass

    @abstractmethod
    def search_users(self, query: str, limit: int = 20) -> List[UserAggregate]:
        """ユーザー検索"""
        pass

    @abstractmethod
    def get_user_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの統計情報を取得"""
        pass

    @abstractmethod
    def bulk_update_relationships(self, relationships: List[Tuple[UserId, UserId, str]]) -> int:
        """複数の関係性を一括更新（フォロー/ブロック/サブスクライブ）"""
        pass

    @abstractmethod
    def cleanup_broken_relationships(self) -> int:
        """無効な関係性をクリーンアップ"""
        pass

    @abstractmethod
    def find_users_by_ids(self, user_ids: List[UserId]) -> List["UserAggregate"]:
        """複数のユーザーIDでユーザーを一括取得"""
        pass

    @abstractmethod
    def generate_user_id(self) -> UserId:
        """ユーザーIDを生成"""
        pass