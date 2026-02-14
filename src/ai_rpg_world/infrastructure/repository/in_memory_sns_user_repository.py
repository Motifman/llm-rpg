"""
InMemorySnsUserRepository - UserAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Tuple, Set
from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemorySnsUserRepository(UserRepository, InMemoryRepositoryBase):
    """UserAggregateを使用するインメモリリポジトリ"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _users(self) -> Dict[UserId, UserAggregate]:
        return self._data_store.sns_users

    @property
    def _username_to_user_id(self) -> Dict[str, UserId]:
        return self._data_store.sns_username_to_user_id

    def find_by_id(self, user_id: UserId) -> Optional[UserAggregate]:
        """ユーザーIDでユーザーを検索"""
        pending = self._get_pending_aggregate(user_id)
        if pending is not None:
            return self._clone(pending)
        return self._users.get(user_id)

    def find_by_ids(self, user_ids: List[UserId]) -> List[UserAggregate]:
        """複数のユーザーIDでユーザーを検索"""
        result = []
        for user_id in user_ids:
            user = self._users.get(user_id)
            if user:
                result.append(user)
        return result

    def find_by_user_name(self, user_name: str) -> Optional[UserAggregate]:
        """ユーザー名でユーザーを検索"""
        user_id = self._username_to_user_id.get(user_name)
        if user_id:
            return self._users.get(user_id)
        return None

    def find_followers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーのフォロワー一覧を取得"""
        followers = []
        for user in self._users.values():
            if any(follow.followee_user_id == user_id for follow in user.follow_relationships):
                followers.append(user.user_id)
        return followers

    def find_followees(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがフォローしているユーザー一覧を取得"""
        user = self._users.get(user_id)
        if not user:
            return []
        return [follow.followee_user_id for follow in user.follow_relationships]

    def find_mutual_follows(self, user_id: UserId) -> List[UserId]:
        """相互フォロー関係を取得"""
        mutual_follows = []
        user = self._users.get(user_id)
        if not user:
            return mutual_follows

        for followee_id in self.find_followees(user_id):
            followee_user = self._users.get(followee_id)
            if followee_user and followee_user.is_following(user_id):
                mutual_follows.append(followee_id)
        return mutual_follows

    def count_followers(self, user_id: UserId) -> int:
        """フォロワー数を取得"""
        return len(self.find_followers(user_id))

    def count_followees(self, user_id: UserId) -> int:
        """フォロー数を取得"""
        return len(self.find_followees(user_id))

    def find_blocked_users(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがブロックしているユーザー一覧を取得"""
        user = self._users.get(user_id)
        if not user:
            return []
        return [block.blocked_user_id for block in user.block_relationships]

    def find_blockers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーをブロックしているユーザー一覧を取得"""
        blockers = []
        for user in self._users.values():
            if user.is_blocked(user_id):
                blockers.append(user.user_id)
        return blockers

    def is_blocked(self, blocker_user_id: UserId, blocked_user_id: UserId) -> bool:
        """ブロック関係の確認"""
        blocker_user = self._users.get(blocker_user_id)
        if not blocker_user:
            return False
        return blocker_user.is_blocked(blocked_user_id)

    def find_subscribers(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーをサブスクライブしているユーザー一覧を取得"""
        subscribers = []
        for user in self._users.values():
            if user.is_subscribed(user_id):
                subscribers.append(user.user_id)
        return subscribers

    def find_subscriptions(self, user_id: UserId) -> List[UserId]:
        """指定ユーザーがサブスクライブしているユーザー一覧を取得"""
        user = self._users.get(user_id)
        if not user:
            return []
        return [subscribe.subscribed_user_id for subscribe in user.subscribe_relationships]

    def is_subscribed(self, subscriber_user_id: UserId, subscribed_user_id: UserId) -> bool:
        """サブスクライブ関係の確認"""
        subscriber_user = self._users.get(subscriber_user_id)
        if not subscriber_user:
            return False
        return subscriber_user.is_subscribed(subscribed_user_id)

    def is_following(self, follower_user_id: UserId, followee_user_id: UserId) -> bool:
        """フォロー関係の確認"""
        follower_user = self._users.get(follower_user_id)
        if not follower_user:
            return False
        return follower_user.is_following(followee_user_id)

    def update_profile(self, user_id: UserId, bio: str, display_name: str) -> Optional[UserAggregate]:
        """ユーザープロフィールを更新"""
        def operation():
            user = self._users.get(user_id)
            if not user:
                return None
            user.update_user_profile(bio, display_name)
            return user
            
        return self._execute_operation(operation)

    def search_users(self, query: str, limit: int = 20) -> List[UserAggregate]:
        """ユーザー検索"""
        result = []
        query_lower = query.lower()
        for user in self._users.values():
            profile_info = user.get_user_profile_info()
            if (query_lower in profile_info["user_name"].lower() or
                query_lower in profile_info["display_name"].lower() or
                query_lower in profile_info["bio"].lower()):
                result.append(user)
                if len(result) >= limit:
                    break
        return result

    def bulk_update_relationships(self, relationships: List[Tuple[UserId, UserId, str]]) -> int:
        """複数の関係性を一括更新（フォロー/ブロック/サブスクライブ）"""
        def operation():
            updated_count = 0
            for from_user_id, to_user_id, relationship_type in relationships:
                from_user = self._users.get(from_user_id)
                to_user = self._users.get(to_user_id)
                if not from_user or not to_user:
                    continue

                if relationship_type == "follow":
                    from_user.follow(to_user_id)
                    updated_count += 1
                elif relationship_type == "block":
                    from_user.block(to_user_id)
                    updated_count += 1
                elif relationship_type == "subscribe":
                    from_user.subscribe(to_user_id)
                    updated_count += 1
            return updated_count
            
        return self._execute_operation(operation)

    def cleanup_broken_relationships(self) -> int:
        """無効な関係性をクリーンアップ（テスト用）"""
        return len(self._users)

    def find_users_by_ids(self, user_ids: List[UserId]) -> List[UserAggregate]:
        """複数のユーザーIDでユーザーを一括取得"""
        return [self._users[user_id] for user_id in user_ids if user_id in self._users]

    def generate_user_id(self) -> UserId:
        """ユーザーIDを生成"""
        user_id = UserId(self._data_store.sns_next_user_id)
        self._data_store.sns_next_user_id += 1
        return user_id

    def save(self, user: UserAggregate) -> UserAggregate:
        """ユーザーを保存"""
        cloned_user = self._clone(user)
        def operation():
            self._users[cloned_user.user_id] = cloned_user
            profile_info = cloned_user.get_user_profile_info()
            self._username_to_user_id[profile_info["user_name"]] = cloned_user.user_id
            return cloned_user
            
        self._register_aggregate(user)
        self._register_pending_if_uow(user.user_id, user)
        return self._execute_operation(operation)

    def delete(self, user_id: UserId) -> bool:
        """ユーザーを削除"""
        def operation():
            if user_id in self._users:
                user = self._users[user_id]
                profile_info = user.get_user_profile_info()
                del self._users[user_id]
                if profile_info["user_name"] in self._username_to_user_id:
                    del self._username_to_user_id[profile_info["user_name"]]
                return True
            return False
            
        return self._execute_operation(operation)

    def find_by_display_name(self, display_name: str) -> Optional[UserAggregate]:
        """表示名でユーザーを検索"""
        for user in self._users.values():
            if user.profile.display_name == display_name:
                return user
        return None

    def get_user_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの統計情報を取得"""
        user = self._users.get(user_id)
        if not user:
            return {}

        follower_count = len([f for f in self._users.values() if any(follow.followee_user_id == user_id for follow in f.follow_relationships)])
        followee_count = len(user.follow_relationships)
        blocked_count = len(user.block_relationships)
        subscription_count = len(user.subscribe_relationships)
        subscriber_count = len([s for s in self._users.values() if any(sub.subscribed_user_id == user_id for sub in s.subscribe_relationships)])

        return {
            "follower_count": follower_count,
            "followee_count": followee_count,
            "blocked_count": blocked_count,
            "subscription_count": subscription_count,
            "subscriber_count": subscriber_count
        }

    def exists_by_id(self, user_id: UserId) -> bool:
        """ユーザーIDが存在するかチェック"""
        return user_id in self._users

    def count(self) -> int:
        """ユーザーの総数を取得"""
        return len(self._users)

    def find_all(self) -> List[UserAggregate]:
        """全てのユーザーを取得"""
        return list(self._users.values())

    def clear(self) -> None:
        """全てのユーザーを削除（テスト用）"""
        self._users.clear()
        self._username_to_user_id.clear()
        self._data_store.sns_next_user_id = 1
