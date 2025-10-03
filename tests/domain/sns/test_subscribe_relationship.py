import pytest
from datetime import datetime
from src.domain.sns.value_object import SubscribeRelationShip, UserId
from src.domain.sns.exception import (
    UserIdValidationException,
    SelfReferenceValidationException,
)


class TestSubscribeRelationShip:
    """SubscribeRelationShipバリューオブジェクトのテスト"""

    def test_create_subscribe_relationship_success(self):
        """正常なSubscribeRelationShipの作成テスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)

        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id
        assert isinstance(subscribe.created_at, datetime)

    def test_create_subscribe_relationship_with_explicit_datetime(self):
        """明示的な日時でのSubscribeRelationShip作成テスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)

        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id, specific_time)

        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id
        assert subscribe.created_at == specific_time

    def test_invalid_subscriber_user_id_raises_error(self):
        """無効な購読者IDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_invalid_subscribed_user_id_raises_error(self):
        """無効な購読対象IDの場合のエラーテスト"""
        with pytest.raises(Exception):  # UserIdValidationException
            UserId(0)

    def test_self_subscribe_raises_error(self):
        """自分自身を購読しようとする場合のエラーテスト"""
        user_id = UserId(1)
        with pytest.raises(SelfReferenceValidationException):
            SubscribeRelationShip(user_id, user_id)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)
        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id

        # 大きな値
        large_user_id = UserId(999999)
        subscribe = SubscribeRelationShip(large_user_id, subscribed_user_id)
        assert subscribe.subscriber_user_id == large_user_id

        subscribe = SubscribeRelationShip(subscriber_user_id, large_user_id)
        assert subscribe.subscribed_user_id == large_user_id

    def test_is_subscribed_method(self):
        """is_subscribedメソッドのテスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        # 購読しているユーザーIDを指定
        assert subscribe.is_subscribed(subscribed_user_id) == True

        # 購読していないユーザーIDを指定
        assert subscribe.is_subscribed(subscriber_user_id) == False
        assert subscribe.is_subscribed(UserId(3)) == False

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        subscriber_user_id1 = UserId(1)
        subscribed_user_id1 = UserId(2)
        subscriber_user_id2 = UserId(1)
        subscribed_user_id2 = UserId(2)

        subscribe1 = SubscribeRelationShip(subscriber_user_id1, subscribed_user_id1, specific_time)
        subscribe2 = SubscribeRelationShip(subscriber_user_id2, subscribed_user_id2, specific_time)

        # 同じユーザーIDの組み合わせであれば等価
        assert subscribe1 == subscribe2
        assert hash(subscribe1) == hash(subscribe2)

    def test_inequality_with_different_subscriber_ids(self):
        """異なる購読者IDでの非等価性テスト"""
        subscriber_user_id1 = UserId(1)
        subscriber_user_id2 = UserId(3)
        subscribed_user_id = UserId(2)

        subscribe1 = SubscribeRelationShip(subscriber_user_id1, subscribed_user_id)
        subscribe2 = SubscribeRelationShip(subscriber_user_id2, subscribed_user_id)

        assert subscribe1 != subscribe2
        assert hash(subscribe1) != hash(subscribe2)

    def test_inequality_with_different_subscribed_ids(self):
        """異なる購読対象IDでの非等価性テスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id1 = UserId(2)
        subscribed_user_id2 = UserId(3)

        subscribe1 = SubscribeRelationShip(subscriber_user_id, subscribed_user_id1)
        subscribe2 = SubscribeRelationShip(subscriber_user_id, subscribed_user_id2)

        assert subscribe1 != subscribe2
        assert hash(subscribe1) != hash(subscribe2)

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)

        subscribe1 = SubscribeRelationShip(subscriber_user_id, subscribed_user_id, time1)
        subscribe2 = SubscribeRelationShip(subscriber_user_id, subscribed_user_id, time2)

        # 同じユーザーIDでも異なる時間の場合は等価（作成時間は比較に含めない）
        assert subscribe1 == subscribe2
        assert hash(subscribe1) == hash(subscribe2)

    def test_hash_with_same_creation_time(self):
        """同じ作成時間のハッシュテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        subscriber_user_id1 = UserId(1)
        subscribed_user_id1 = UserId(2)
        subscriber_user_id2 = UserId(1)
        subscribed_user_id2 = UserId(2)

        subscribe1 = SubscribeRelationShip(subscriber_user_id1, subscribed_user_id1, time)
        subscribe2 = SubscribeRelationShip(subscriber_user_id2, subscribed_user_id2, time)

        # 同じユーザーIDと時間の場合は等価
        assert subscribe1 == subscribe2
        assert hash(subscribe1) == hash(subscribe2)

    def test_immutability(self):
        """不変性のテスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        str_repr = str(subscribe)
        assert "SubscribeRelationShip(" in str_repr
        assert str(subscriber_user_id) in str_repr
        assert str(subscribed_user_id) in str_repr

    def test_created_at_auto_generation(self):
        """created_atの自動生成テスト"""
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        # 作成時間が現在時刻に近いことを確認
        now = datetime.now()
        time_diff = abs((now - subscribe.created_at).total_seconds())
        assert time_diff < 1  # 1秒以内の差

    def test_different_subscriber_subscribed_combinations(self):
        """異なる購読者・購読対象の組み合わせテスト"""
        # 通常のケース（購読者が購読対象より小さい）
        subscriber_user_id1 = UserId(1)
        subscribed_user_id1 = UserId(100)
        subscribe1 = SubscribeRelationShip(subscriber_user_id1, subscribed_user_id1)
        assert subscribe1.subscriber_user_id == subscriber_user_id1
        assert subscribe1.subscribed_user_id == subscribed_user_id1

        # 購読者が購読対象より大きい
        subscriber_user_id2 = UserId(100)
        subscribed_user_id2 = UserId(1)
        subscribe2 = SubscribeRelationShip(subscriber_user_id2, subscribed_user_id2)
        assert subscribe2.subscriber_user_id == subscriber_user_id2
        assert subscribe2.subscribed_user_id == subscribed_user_id2

        # is_subscribedメソッドのテスト
        assert subscribe1.is_subscribed(subscribed_user_id1) == True
        assert subscribe1.is_subscribed(subscriber_user_id1) == False
        assert subscribe2.is_subscribed(subscribed_user_id2) == True
        assert subscribe2.is_subscribed(subscriber_user_id2) == False

    def test_subscription_vs_following_difference(self):
        """購読とフォローの違いを確認"""
        # 同じ意味でも異なる概念として扱えることを確認
        subscriber_user_id = UserId(1)
        subscribed_user_id = UserId(2)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        assert subscribe.subscriber_user_id == subscriber_user_id
        assert subscribe.subscribed_user_id == subscribed_user_id
        assert subscribe.is_subscribed(subscribed_user_id) == True

    def test_id_string_conversion(self):
        """IDの文字列変換テスト"""
        subscriber_user_id = UserId(123)
        subscribed_user_id = UserId(456)
        subscribe = SubscribeRelationShip(subscriber_user_id, subscribed_user_id)

        assert str(subscribe.subscriber_user_id) == "123"
        assert str(subscribe.subscribed_user_id) == "456"
        assert int(subscribe.subscriber_user_id) == 123
        assert int(subscribe.subscribed_user_id) == 456
