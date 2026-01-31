import pytest
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.domain.sns.enum.sns_enum import UserRelationshipType


class TestInMemorySnsUserRepository:
    def setup_method(self):
        """各テストメソッドの前に実行される"""
        self.repository = InMemorySnsUserRepository()

    def test_find_by_id(self):
        """ユーザーID検索テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 存在するユーザー
        user = self.repository.find_by_id(UserId(1))
        assert user is not None
        assert user.user_id.value == 1
        assert user.get_user_profile_info()["user_name"] == "hero_user"

        # 存在しないユーザー
        user = self.repository.find_by_id(UserId(999))
        assert user is None

    def test_find_by_ids(self):
        """複数ユーザーID検索テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        users = self.repository.find_by_ids([UserId(1), UserId(2), UserId(3)])
        assert len(users) == 3
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(2), UserId(3)}

        # 存在しないユーザーIDを含む場合
        users = self.repository.find_by_ids([UserId(1), UserId(999), UserId(3)])
        assert len(users) == 2
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(3)}

    def test_find_by_user_name(self):
        """ユーザー名検索テスト"""
        # 存在するユーザー
        user = self.repository.find_by_user_name("hero_user")
        assert user is not None
        assert user.user_id.value == 1

        # 存在しないユーザー
        user = self.repository.find_by_user_name("nonexistent_user")
        assert user is None

    def test_find_followers(self):
        """フォロワー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）のフォロワー
        followers = self.repository.find_followers(UserId(1))
        # 魔法使い（2）、戦士（3）、盗賊（4）、僧侶（5）が勇者をフォロー
        assert set(f.value for f in followers) == {2, 3, 4, 5}

        # 魔法使い（ユーザー2）のフォロワー
        followers = self.repository.find_followers(UserId(2))
        # 勇者（1）、僧侶（5）が魔法使いをフォロー
        assert set(f.value for f in followers) == {1, 5}

    def test_find_followees(self):
        """フォロー中ユーザー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）のフォロー中ユーザー
        followees = self.repository.find_followees(UserId(1))
        # 魔法使い（2）と戦士（3）をフォロー
        assert set(f.value for f in followees) == {2, 3}

        # 魔法使い（ユーザー2）のフォロー中ユーザー
        followees = self.repository.find_followees(UserId(2))
        # 勇者（1）と戦士（3）をフォロー
        assert set(f.value for f in followees) == {1, 3}

        # 商人（ユーザー6）のフォロー中ユーザー（誰もフォローしていない）
        followees = self.repository.find_followees(UserId(6))
        assert followees == []

    def test_find_mutual_follows(self):
        """相互フォロー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）と魔法使い（ユーザー2）は相互フォロー
        mutual_follows = self.repository.find_mutual_follows(UserId(1))
        assert UserId(2) in mutual_follows  # 魔法使いとの相互フォロー

        # 魔法使い（ユーザー2）と勇者（ユーザー1）は相互フォロー
        mutual_follows = self.repository.find_mutual_follows(UserId(2))
        assert UserId(1) in mutual_follows  # 勇者との相互フォロー

        # 戦士（ユーザー3）と勇者（ユーザー1）は相互フォロー
        mutual_follows = self.repository.find_mutual_follows(UserId(3))
        assert UserId(1) in mutual_follows  # 勇者との相互フォロー

    def test_count_followers(self):
        """フォロワー数取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        assert self.repository.count_followers(UserId(1)) == 4  # 勇者のフォロワー数
        assert self.repository.count_followers(UserId(2)) == 2  # 魔法使いのフォロワー数
        assert self.repository.count_followers(UserId(3)) == 2  # 戦士のフォロワー数（勇者と魔法使い）
        assert self.repository.count_followers(UserId(6)) == 0  # 商人のフォロワー数

    def test_count_followees(self):
        """フォロー数取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        assert self.repository.count_followees(UserId(1)) == 2  # 勇者のフォロー数
        assert self.repository.count_followees(UserId(2)) == 2  # 魔法使いのフォロー数
        assert self.repository.count_followees(UserId(3)) == 1  # 戦士のフォロー数
        assert self.repository.count_followees(UserId(6)) == 0  # 商人のフォロー数

    def test_find_blocked_users(self):
        """ブロック中ユーザー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 魔法使い（ユーザー2）のブロック中ユーザー
        blocked_users = self.repository.find_blocked_users(UserId(2))
        assert [u.value for u in blocked_users] == [4]  # 盗賊をブロック

        # 商人（ユーザー6）のブロック中ユーザー
        blocked_users = self.repository.find_blocked_users(UserId(6))
        assert [u.value for u in blocked_users] == [1]  # 勇者をブロック

        # ブロックしていないユーザーの場合
        blocked_users = self.repository.find_blocked_users(UserId(1))
        assert blocked_users == []

    def test_find_blockers(self):
        """ブロックしているユーザー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 盗賊（ユーザー4）のブロック者
        blockers = self.repository.find_blockers(UserId(4))
        assert [u.value for u in blockers] == [2]  # 魔法使いにブロックされている

        # 勇者（ユーザー1）のブロック者
        blockers = self.repository.find_blockers(UserId(1))
        assert [u.value for u in blockers] == [6]  # 商人にブロックされている

        # ブロックされていないユーザーの場合
        blockers = self.repository.find_blockers(UserId(3))
        assert blockers == []

    def test_is_blocked(self):
        """ブロック関係確認テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        assert self.repository.is_blocked(UserId(2), UserId(4)) == True   # 魔法使い -> 盗賊
        assert self.repository.is_blocked(UserId(6), UserId(1)) == True   # 商人 -> 勇者
        assert self.repository.is_blocked(UserId(1), UserId(2)) == False  # 勇者 -> 魔法使い（ブロックなし）
        assert self.repository.is_blocked(UserId(1), UserId(4)) == False  # 勇者 -> 盗賊（ブロックなし）

    def test_find_subscribers(self):
        """購読者取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）の購読者
        subscribers = self.repository.find_subscribers(UserId(1))
        # 魔法使い（2）と僧侶（5）が勇者を購読
        assert set(s.value for s in subscribers) == {2, 5}

        # 魔法使い（ユーザー2）の購読者
        subscribers = self.repository.find_subscribers(UserId(2))
        # 勇者（1）が魔法使いを購読
        assert [s.value for s in subscribers] == [1]

        # 購読されていないユーザーの場合
        subscribers = self.repository.find_subscribers(UserId(3))
        assert subscribers == []

    def test_find_subscriptions(self):
        """購読中ユーザー取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）の購読中ユーザー
        subscriptions = self.repository.find_subscriptions(UserId(1))
        assert [s.value for s in subscriptions] == [2]  # 魔法使いを購読

        # 魔法使い（ユーザー2）の購読中ユーザー
        subscriptions = self.repository.find_subscriptions(UserId(2))
        assert [s.value for s in subscriptions] == [1]  # 勇者を購読

        # 購読していないユーザーの場合
        subscriptions = self.repository.find_subscriptions(UserId(3))
        assert subscriptions == []

    def test_is_subscribed(self):
        """購読関係確認テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        assert self.repository.is_subscribed(UserId(1), UserId(2)) == True   # 勇者 -> 魔法使い
        assert self.repository.is_subscribed(UserId(2), UserId(1)) == True   # 魔法使い -> 勇者
        assert self.repository.is_subscribed(UserId(1), UserId(3)) == False  # 勇者 -> 戦士（購読なし）
        assert self.repository.is_subscribed(UserId(3), UserId(1)) == False  # 戦士 -> 勇者（購読なし）

    def test_update_profile(self):
        """プロフィール更新テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 既存ユーザーのプロフィール更新
        updated_user = self.repository.update_profile(UserId(1), "新しい自己紹介", "新勇者")
        assert updated_user is not None
        profile_info = updated_user.get_user_profile_info()
        assert profile_info["bio"] == "新しい自己紹介"
        assert profile_info["display_name"] == "新勇者"

        # 存在しないユーザーの更新
        updated_user = self.repository.update_profile(UserId(999), "テスト", "テストユーザー")
        assert updated_user is None

    def test_search_users(self):
        """ユーザー検索テスト"""
        # 名前で検索
        results = self.repository.search_users("hero")
        assert len(results) == 1
        assert results[0].user_id.value == 1

        # 表示名で検索
        results = self.repository.search_users("勇者")
        assert len(results) == 1
        assert results[0].user_id.value == 1

        # 自己紹介で検索
        results = self.repository.search_users("魔法")
        assert len(results) == 1
        assert results[0].user_id.value == 2

        # 複数結果の検索
        results = self.repository.search_users("修行")
        assert len(results) == 1  # 戦士のみ

        # 結果なしの場合
        results = self.repository.search_users("存在しない")
        assert len(results) == 0

        # 件数制限テスト
        results = self.repository.search_users("user", limit=2)
        assert len(results) <= 2

    def test_get_user_stats(self):
        """ユーザー統計情報取得テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 勇者（ユーザー1）の統計
        stats = self.repository.get_user_stats(UserId(1))
        assert stats["follower_count"] == 4
        assert stats["followee_count"] == 2
        assert stats["blocked_count"] == 0
        assert stats["subscription_count"] == 1
        assert stats["subscriber_count"] == 2

        # 魔法使い（ユーザー2）の統計
        stats = self.repository.get_user_stats(UserId(2))
        assert stats["follower_count"] == 2
        assert stats["followee_count"] == 2
        assert stats["blocked_count"] == 1
        assert stats["subscription_count"] == 1
        assert stats["subscriber_count"] == 1

        # 商人（ユーザー6）の統計
        stats = self.repository.get_user_stats(UserId(6))
        assert stats["follower_count"] == 0
        assert stats["followee_count"] == 0
        assert stats["blocked_count"] == 1
        assert stats["subscription_count"] == 0
        assert stats["subscriber_count"] == 0

        # 存在しないユーザーの統計
        stats = self.repository.get_user_stats(UserId(999))
        assert stats == {}

    def test_bulk_update_relationships(self):
        """一括関係性更新テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        # 新しい関係性を追加
        relationships = [
            (UserId(3), UserId(2), "follow"),    # 戦士 -> 魔法使いをフォロー
            (UserId(4), UserId(2), "follow"),    # 盗賊 -> 魔法使いをフォロー
            (UserId(5), UserId(3), "follow"),    # 僧侶 -> 戦士をフォロー
        ]

        updated_count = self.repository.bulk_update_relationships(relationships)
        assert updated_count == 3

        # 結果の検証
        assert self.repository.is_following(UserId(3), UserId(2)) == True  # 戦士 -> 魔法使い
        assert self.repository.is_following(UserId(4), UserId(2)) == True  # 盗賊 -> 魔法使い
        assert self.repository.is_following(UserId(5), UserId(3)) == True  # 僧侶 -> 戦士

    def test_cleanup_broken_relationships(self):
        """無効な関係性クリーンアップテスト"""
        # 全ての関係性が有効なので、クリーンアップ後も同じ数
        cleaned_count = self.repository.cleanup_broken_relationships()
        assert cleaned_count == 6  # 6人のユーザーがいる

    def test_generate_user_id(self):
        """ユーザーID生成テスト"""
        next_id = self.repository.generate_user_id()
        assert next_id.value == 7  # サンプルデータで6人いるので次は7

        next_id2 = self.repository.generate_user_id()
        assert next_id2.value == 8  # 次は8

    def test_save_and_delete(self):
        """保存・削除テスト"""
        from ai_rpg_world.domain.sns.entity.sns_user import SnsUser
        from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile
        from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate

        # 新しいユーザーを作成
        new_profile = UserProfile("test_user", "テストユーザー", "テスト用のユーザーです")
        new_sns_user = SnsUser(7, new_profile)
        new_user = UserAggregate(7, new_sns_user, [], [], [])

        # 保存
        self.repository.save(new_user)
        assert self.repository.find_by_id(7) is not None
        assert self.repository.find_by_user_name("test_user") is not None

        # 削除
        result = self.repository.delete(7)
        assert result == True
        assert self.repository.find_by_id(7) is None
        assert self.repository.find_by_user_name("test_user") is None

        # 存在しないユーザーの削除
        result = self.repository.delete(999)
        assert result == False

    def test_exists_by_id(self):
        """ユーザー存在確認テスト"""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId

        assert self.repository.exists_by_id(UserId(1)) == True
        assert self.repository.exists_by_id(UserId(999)) == False

    def test_count(self):
        """ユーザー総数取得テスト"""
        assert self.repository.count() == 6  # サンプルデータで6人

    def test_find_all(self):
        """全ユーザー取得テスト"""
        all_users = self.repository.find_all()
        assert len(all_users) == 6
        user_ids = [user.user_id.value for user in all_users]
        assert set(user_ids) == {1, 2, 3, 4, 5, 6}

    def test_clear(self):
        """クリアテスト（テスト用）"""
        self.repository.clear()
        assert self.repository.count() == 0
        assert len(self.repository._username_to_user_id) == 0
