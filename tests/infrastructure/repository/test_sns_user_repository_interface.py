import pytest
from typing import List
from src.domain.sns.repository.sns_user_repository import UserRepository
from src.domain.sns.value_object import UserId


class _TestUserRepositoryInterface:
    """UserRepositoryインターフェースのテスト基幹クラス"""

    @pytest.fixture
    def repository(self) -> UserRepository:
        """具象実装を返すfixture - サブクラスでオーバーライド"""
        raise NotImplementedError("サブクラスで実装してください")

    def test_find_by_id_existing_user(self, repository):
        """既存ユーザーのID検索テスト"""
        from src.domain.sns.value_object import UserId
        user = repository.find_by_id(UserId(1))
        assert user is not None
        assert user.user_id == UserId(1)
        assert user.get_user_profile_info()["user_name"] == "hero_user"

    def test_find_by_id_nonexistent_user(self, repository):
        """存在しないユーザーのID検索テスト"""
        from src.domain.sns.value_object import UserId
        user = repository.find_by_id(UserId(999))
        assert user is None

    def test_find_by_user_name_existing_user(self, repository):
        """既存ユーザーのユーザー名検索テスト"""
        from src.domain.sns.value_object import UserId
        user = repository.find_by_user_name("hero_user")
        assert user is not None
        assert user.user_id == UserId(1)

    def test_find_by_user_name_nonexistent_user(self, repository):
        """存在しないユーザーのユーザー名検索テスト"""
        user = repository.find_by_user_name("nonexistent_user")
        assert user is None

    def test_find_by_ids_multiple_users(self, repository):
        """複数ユーザーのID検索テスト"""
        from src.domain.sns.value_object import UserId
        users = repository.find_by_ids([UserId(1), UserId(2), UserId(3)])
        assert len(users) == 3
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(2), UserId(3)}

    def test_find_by_ids_with_invalid_ids(self, repository):
        """無効なIDを含む複数ユーザー検索テスト"""
        from src.domain.sns.value_object import UserId
        users = repository.find_by_ids([UserId(1), UserId(999), UserId(3)])
        assert len(users) == 2
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(3)}

    def test_find_followers(self, repository):
        """フォロワー取得テスト"""
        followers = repository.find_followers(UserId(1))
        assert isinstance(followers, List)
        # 勇者のフォロワー：魔法使い(2), 戦士(3), 盗賊(4), 僧侶(5)
        assert set(followers) == {UserId(2), UserId(3), UserId(4), UserId(5)}

    def test_find_followees(self, repository):
        """フォロー中ユーザー取得テスト"""
        followees = repository.find_followees(UserId(1))
        assert isinstance(followees, List)
        # 勇者のフォロー：魔法使い(2), 戦士(3)
        assert set(followees) == {UserId(2), UserId(3)}

    def test_find_mutual_follows(self, repository):
        """相互フォロー取得テスト"""
        mutual_follows = repository.find_mutual_follows(UserId(1))
        assert isinstance(mutual_follows, List)
        # 勇者と魔法使いは相互フォロー
        assert UserId(2) in mutual_follows

    def test_count_followers(self, repository):
        """フォロワー数取得テスト"""
        count = repository.count_followers(UserId(1))
        assert count == 4  # 勇者のフォロワー数

    def test_count_followees(self, repository):
        """フォロー数取得テスト"""
        count = repository.count_followees(UserId(1))
        assert count == 2  # 勇者のフォロー数

    def test_find_blocked_users(self, repository):
        """ブロック中ユーザー取得テスト"""
        blocked_users = repository.find_blocked_users(UserId(2))
        assert isinstance(blocked_users, List)
        # 魔法使いは盗賊(4)をブロック
        assert blocked_users == [UserId(4)]

    def test_find_blockers(self, repository):
        """ブロックしているユーザー取得テスト"""
        blockers = repository.find_blockers(UserId(4))
        assert isinstance(blockers, List)
        # 盗賊は魔法使い(2)にブロックされている
        assert blockers == [UserId(2)]

    def test_is_blocked(self, repository):
        """ブロック関係確認テスト"""
        assert repository.is_blocked(UserId(2), UserId(4)) == True   # 魔法使い -> 盗賊
        assert repository.is_blocked(UserId(1), UserId(2)) == False  # 勇者 -> 魔法使い

    def test_find_subscribers(self, repository):
        """購読者取得テスト"""
        subscribers = repository.find_subscribers(UserId(1))
        assert isinstance(subscribers, List)
        # 勇者の購読者：魔法使い(2), 僧侶(5)
        assert set(subscribers) == {UserId(2), UserId(5)}

    def test_find_subscriptions(self, repository):
        """購読中ユーザー取得テスト"""
        subscriptions = repository.find_subscriptions(UserId(1))
        assert isinstance(subscriptions, List)
        # 勇者の購読：魔法使い(2)
        assert subscriptions == [UserId(2)]

    def test_is_subscribed(self, repository):
        """購読関係確認テスト"""
        assert repository.is_subscribed(UserId(1), UserId(2)) == True   # 勇者 -> 魔法使い
        assert repository.is_subscribed(UserId(1), UserId(3)) == False  # 勇者 -> 戦士

    def test_search_users_by_name(self, repository):
        """ユーザー名での検索テスト"""
        results = repository.search_users("hero")
        assert len(results) == 1
        assert results[0].user_id == UserId(1)

    def test_search_users_by_display_name(self, repository):
        """表示名での検索テスト"""
        results = repository.search_users("勇者")
        assert len(results) == 1
        assert results[0].user_id == UserId(1)

    def test_search_users_by_bio(self, repository):
        """自己紹介文での検索テスト"""
        results = repository.search_users("魔法")
        assert len(results) == 1
        assert results[0].user_id == UserId(2)

    def test_get_user_stats(self, repository):
        """ユーザー統計情報取得テスト"""
        stats = repository.get_user_stats(UserId(1))
        assert isinstance(stats, dict)
        assert "follower_count" in stats
        assert "followee_count" in stats
        assert stats["follower_count"] == 4
        assert stats["followee_count"] == 2

    def test_find_users_by_ids(self, repository):
        """複数ユーザーIDでの一括取得テスト"""
        users = repository.find_users_by_ids([UserId(1), UserId(2)])
        assert len(users) == 2
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(2)}

    def test_generate_user_id(self, repository):
        """ユーザーID生成テスト"""
        user_id = repository.generate_user_id()
        assert isinstance(user_id, UserId)
        assert user_id.value >= 7  # サンプルデータで6人いるので7以上

    def test_exists_by_id(self, repository):
        """ユーザー存在確認テスト"""
        assert repository.exists_by_id(UserId(1)) == True
        assert repository.exists_by_id(UserId(999)) == False

    def test_count(self, repository):
        """総ユーザー数取得テスト"""
        count = repository.count()
        assert count == 6  # サンプルデータで6人

    def test_find_all(self, repository):
        """全ユーザー取得テスト"""
        users = repository.find_all()
        assert len(users) == 6
        user_ids = [user.user_id for user in users]
        assert set(user_ids) == {UserId(1), UserId(2), UserId(3), UserId(4), UserId(5), UserId(6)}
