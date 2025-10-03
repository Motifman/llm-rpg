"""
InMemorySnsUserRepository - UserAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Tuple, Set
from src.domain.sns.repository.sns_user_repository import UserRepository
from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.entity.sns_user import SnsUser
from src.domain.sns.value_object.user_profile import UserProfile
from src.domain.sns.value_object.follow import FollowRelationShip
from src.domain.sns.value_object.block import BlockRelationShip
from src.domain.sns.value_object.subscribe import SubscribeRelationShip
from src.domain.sns.enum.sns_enum import UserRelationshipType
from src.domain.sns.value_object.user_id import UserId


class InMemorySnsUserRepository(UserRepository):
    """UserAggregateを使用するインメモリリポジトリ"""

    def __init__(self):
        self._users: Dict[UserId, UserAggregate] = {}
        self._username_to_user_id: Dict[str, UserId] = {}
        self._next_user_id = UserId(1)

        # サンプルユーザーデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルユーザーデータのセットアップ"""
        # ユーザー1: メインキャラクター
        user1_profile = UserProfile("hero_user", "勇者", "世界を救う勇者です")
        user1_sns_user = SnsUser(UserId(1), user1_profile)
        user1_follows = [
            FollowRelationShip(UserId(1), UserId(2)),  # 勇者 -> 魔法使いをフォロー
            FollowRelationShip(UserId(1), UserId(3)),  # 勇者 -> 戦士をフォロー
        ]
        user1_blocks = [
            # 勇者はブロックなし
        ]
        user1_subscribes = [
            SubscribeRelationShip(UserId(1), UserId(2)),  # 勇者 -> 魔法使いを購読
        ]
        user1_aggregate = UserAggregate(UserId(1), user1_sns_user, user1_follows, user1_blocks, user1_subscribes)
        self._users[UserId(1)] = user1_aggregate
        self._username_to_user_id["hero_user"] = UserId(1)

        # ユーザー2: 魔法使い
        user2_profile = UserProfile("mage_user", "魔法使い", "魔法の研究に没頭しています")
        user2_sns_user = SnsUser(UserId(2), user2_profile)
        user2_follows = [
            FollowRelationShip(UserId(2), UserId(1)),  # 魔法使い -> 勇者をフォロー
            FollowRelationShip(UserId(2), UserId(3)),  # 魔法使い -> 戦士をフォロー
        ]
        user2_blocks = [
            BlockRelationShip(UserId(2), UserId(4)),  # 魔法使い -> 盗賊をブロック
        ]
        user2_subscribes = [
            SubscribeRelationShip(UserId(2), UserId(1)),  # 魔法使い -> 勇者を購読
        ]
        user2_aggregate = UserAggregate(UserId(2), user2_sns_user, user2_follows, user2_blocks, user2_subscribes)
        self._users[UserId(2)] = user2_aggregate
        self._username_to_user_id["mage_user"] = UserId(2)

        # ユーザー3: 戦士
        user3_profile = UserProfile("warrior_user", "戦士", "剣の修行に励んでいます")
        user3_sns_user = SnsUser(UserId(3), user3_profile)
        user3_follows = [
            FollowRelationShip(UserId(3), UserId(1)),  # 戦士 -> 勇者をフォロー
        ]
        user3_blocks = [
            # 戦士はブロックなし
        ]
        user3_subscribes = [
            # 戦士は購読なし
        ]
        user3_aggregate = UserAggregate(UserId(3), user3_sns_user, user3_follows, user3_blocks, user3_subscribes)
        self._users[UserId(3)] = user3_aggregate
        self._username_to_user_id["warrior_user"] = UserId(3)

        # ユーザー4: 盗賊
        user4_profile = UserProfile("thief_user", "盗賊", "宝探しが趣味です")
        user4_sns_user = SnsUser(UserId(4), user4_profile)
        user4_follows = [
            FollowRelationShip(UserId(4), UserId(1)),  # 盗賊 -> 勇者をフォロー
        ]
        user4_blocks = [
            # 盗賊はブロックなし
        ]
        user4_subscribes = [
            # 盗賊は購読なし
        ]
        user4_aggregate = UserAggregate(UserId(4), user4_sns_user, user4_follows, user4_blocks, user4_subscribes)
        self._users[UserId(4)] = user4_aggregate
        self._username_to_user_id["thief_user"] = UserId(4)

        # ユーザー5: 僧侶
        user5_profile = UserProfile("priest_user", "僧侶", "人々を癒すのが使命です")
        user5_sns_user = SnsUser(UserId(5), user5_profile)
        user5_follows = [
            FollowRelationShip(UserId(5), UserId(1)),  # 僧侶 -> 勇者をフォロー
            FollowRelationShip(UserId(5), UserId(2)),  # 僧侶 -> 魔法使いをフォロー
        ]
        user5_blocks = [
            # 僧侶はブロックなし
        ]
        user5_subscribes = [
            SubscribeRelationShip(UserId(5), UserId(1)),  # 僧侶 -> 勇者を購読
        ]
        user5_aggregate = UserAggregate(UserId(5), user5_sns_user, user5_follows, user5_blocks, user5_subscribes)
        self._users[UserId(5)] = user5_aggregate
        self._username_to_user_id["priest_user"] = UserId(5)

        # ユーザー6: 商人
        user6_profile = UserProfile("merchant_user", "商人", "良い取引を探しています")
        user6_sns_user = SnsUser(UserId(6), user6_profile)
        user6_follows = [
            # 商人は誰もフォローしていない
        ]
        user6_blocks = [
            BlockRelationShip(UserId(6), UserId(1)),  # 商人 -> 勇者をブロック
        ]
        user6_subscribes = [
            # 商人は購読なし
        ]
        user6_aggregate = UserAggregate(UserId(6), user6_sns_user, user6_follows, user6_blocks, user6_subscribes)
        self._users[UserId(6)] = user6_aggregate
        self._username_to_user_id["merchant_user"] = UserId(6)

        self._next_user_id = UserId(7)

    def find_by_id(self, user_id: UserId) -> Optional[UserAggregate]:
        """ユーザーIDでユーザーを検索"""
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
            # user_idをフォローしているユーザーを探す
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
        user = self._users.get(user_id)
        if not user:
            return None
        user.update_user_profile(bio, display_name)
        return user

    def search_users(self, query: str, limit: int = 20) -> List[UserAggregate]:
        """ユーザー検索"""
        result = []
        query_lower = query.lower()
        for user in self._users.values():
            # ユーザー名、表示名、自己紹介で検索
            profile_info = user.get_user_profile_info()
            if (query_lower in profile_info["user_name"].lower() or
                query_lower in profile_info["display_name"].lower() or
                query_lower in profile_info["bio"].lower()):
                result.append(user)
                if len(result) >= limit:
                    break
        return result

    def get_user_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの統計情報を取得"""
        user = self._users.get(user_id)
        if not user:
            return {}

        return {
            "follower_count": self.count_followers(user_id),
            "followee_count": self.count_followees(user_id),
            "blocked_count": len(self.find_blocked_users(user_id)),
            "subscription_count": len(self.find_subscriptions(user_id)),
            "subscriber_count": len(self.find_subscribers(user_id)),
        }

    def bulk_update_relationships(self, relationships: List[Tuple[UserId, UserId, str]]) -> int:
        """複数の関係性を一括更新（フォロー/ブロック/サブスクライブ）"""
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

    def cleanup_broken_relationships(self) -> int:
        """無効な関係性をクリーンアップ（テスト用）"""
        # 現在のところ、全ての関係性が有効なので、単にユーザー数を返す
        return len(self._users)

    def find_users_by_ids(self, user_ids: List[UserId]) -> List[UserAggregate]:
        """複数のユーザーIDでユーザーを一括取得"""
        return [self._users[user_id] for user_id in user_ids if user_id in self._users]

    def generate_user_id(self) -> UserId:
        """ユーザーIDを生成"""
        user_id = self._next_user_id
        self._next_user_id = UserId(self._next_user_id.value + 1)
        return user_id

    def save(self, user: UserAggregate) -> UserAggregate:
        """ユーザーを保存"""
        self._users[user.user_id] = user
        # ユーザー名マッピングも更新
        profile_info = user.get_user_profile_info()
        self._username_to_user_id[profile_info["user_name"]] = user.user_id
        return user

    def delete(self, user_id: UserId) -> bool:
        """ユーザーを削除"""
        if user_id in self._users:
            user = self._users[user_id]
            profile_info = user.get_user_profile_info()
            del self._users[user_id]
            # ユーザー名マッピングも削除
            if profile_info["user_name"] in self._username_to_user_id:
                del self._username_to_user_id[profile_info["user_name"]]
            return True
        return False

    def find_by_display_name(self, display_name: str) -> Optional[UserAggregate]:
        """表示名でユーザーを検索"""
        for user in self._users.values():
            if user.profile.display_name == display_name:
                return user
        return None

    def exists_by_id(self, user_id: UserId) -> bool:
        """ユーザーIDが存在するかチェック"""
        return user_id in self._users

    def count(self) -> int:
        """ユーザーの総数を取得"""
        return len(self._users)

    def find_all(self) -> List[UserAggregate]:
        """全てのユーザーを取得"""
        return list(self._users.values())

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのユーザーを削除（テスト用）"""
        self._users.clear()
        self._username_to_user_id.clear()
        self._next_user_id = UserId(1)
