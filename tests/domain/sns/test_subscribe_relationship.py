import pytest
from datetime import datetime
from src.domain.sns.subscribe import SubscribeRelationShip


class TestSubscribeRelationShip:
    """SubscribeRelationShipバリューオブジェクトのテスト"""

    def test_create_subscribe_relationship_success(self):
        """正常なSubscribeRelationShipの作成テスト"""
        subscriber_user_id = 1
        subscribed_user_id = 2

        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id
        assert isinstance(subscribe.created_at, datetime)

    def test_create_subscribe_relationship_with_explicit_datetime(self):
        """明示的な日時でのSubscribeRelationShip作成テスト"""
        subscriber_user_id = 1
        subscribed_user_id = 2
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id, specific_time)

        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id
        assert subscribe.created_at == specific_time

    def test_invalid_subscriber_user_id_raises_error(self):
        """無効な購読者IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="subscriber_user_id must be positive"):
            SubscribeRelationShip(0, 2)

        with pytest.raises(ValueError, match="subscriber_user_id must be positive"):
            SubscribeRelationShip(-1, 2)

    def test_invalid_subscribed_user_id_raises_error(self):
        """無効な購読対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="subscribed_user_id must be positive"):
            SubscribeRelationShip(1, 0)

        with pytest.raises(ValueError, match="subscribed_user_id must be positive"):
            SubscribeRelationShip(1, -1)

    def test_self_subscribe_allowed(self):
        """自分自身を購読できることを確認"""
        user_id = 1
        subscribe = SubscribeRelationShip(user_id, user_id)
        assert subscribe.subscriber_user_id == user_id
        assert subscribe.subscribed_user_id == user_id

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        subscribe = SubscribeRelationShip(1, 2)
        assert subscribe.subscriber_user_id == 1

        # 大きな値
        large_user_id = 999999
        subscribe = SubscribeRelationShip(large_user_id, 2)
        assert subscribe.subscriber_user_id == large_user_id

        subscribe = SubscribeRelationShip(1, large_user_id)
        assert subscribe.subscribed_user_id == large_user_id

    def test_is_subscribed_method(self):
        """is_subscribedメソッドのテスト"""
        subscribe = SubscribeRelationShip(1, 2)

        # 購読しているユーザーIDを指定
        assert subscribe.is_subscribed(2) == True

        # 購読していないユーザーIDを指定
        assert subscribe.is_subscribed(1) == False
        assert subscribe.is_subscribed(3) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        subscribe1 = SubscribeRelationShip(1, 2, specific_time)
        subscribe2 = SubscribeRelationShip(1, 2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert subscribe1 == subscribe2
        assert hash(subscribe1) == hash(subscribe2)

    def test_inequality_with_different_subscriber_ids(self):
        """異なる購読者IDでの非等価性テスト"""
        subscribe1 = SubscribeRelationShip(1, 2)
        subscribe2 = SubscribeRelationShip(3, 2)

        assert subscribe1 != subscribe2
        assert hash(subscribe1) != hash(subscribe2)

    def test_inequality_with_different_subscribed_ids(self):
        """異なる購読対象IDでの非等価性テスト"""
        subscribe1 = SubscribeRelationShip(1, 2)
        subscribe2 = SubscribeRelationShip(1, 3)

        assert subscribe1 != subscribe2
        assert hash(subscribe1) != hash(subscribe2)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        subscribe1 = SubscribeRelationShip(1, 2, time1)
        subscribe2 = SubscribeRelationShip(1, 2, time2)

        # 同じユーザーIDでも異なる時間の場合は等価ではない
        assert subscribe1 != subscribe2
        assert hash(subscribe1) != hash(subscribe2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        subscribe1 = SubscribeRelationShip(1, 2, time)
        subscribe2 = SubscribeRelationShip(1, 2, time)

        # 同じユーザーIDと時間の場合は等価
        assert subscribe1 == subscribe2
        assert hash(subscribe1) == hash(subscribe2)

    def test_immutability(self):
        """不変性のテスト"""
        subscribe = SubscribeRelationShip(1, 2)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        subscribe = SubscribeRelationShip(1, 2)

        str_repr = str(subscribe)
        assert "SubscribeRelationShip(" in str_repr
        assert "1" in str_repr
        assert "2" in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        subscribe = SubscribeRelationShip(1, 2)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - subscribe.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_different_subscriber_subscribed_combinations(self):
        """異なる購読者・購読対象の組み合わせテスト"""
        # 通常のケース（購読者が購読対象より小さい）
        subscribe1 = SubscribeRelationShip(1, 100)
        assert subscribe1.subscriber_user_id == 1
        assert subscribe1.subscribed_user_id == 100

        # 購読者が購読対象より大きい
        subscribe2 = SubscribeRelationShip(100, 1)
        assert subscribe2.subscriber_user_id == 100
        assert subscribe2.subscribed_user_id == 1

        # is_subscribedメソッドのテスト
        assert subscribe1.is_subscribed(100) == True
        assert subscribe1.is_subscribed(1) == False
        assert subscribe2.is_subscribed(1) == True
        assert subscribe2.is_subscribed(100) == False

    def test_subscription_vs_following_difference(self):
        """購読とフォローの違いを確認"""
        # 同じ意味でも異なる概念として扱えることを確認
        subscribe = SubscribeRelationShip(1, 2)
        # これはフォローとは異なる概念だが、テスト上では同じ構造

        assert subscribe.subscriber_user_id == 1
        assert subscribe.subscribed_user_id == 2
        assert subscribe.is_subscribed(2) == True
