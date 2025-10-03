import pytest
from src.domain.sns.value_object.notification_content import NotificationContent
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.value_object.reply_id import ReplyId
from src.domain.sns.exception import NotificationContentValidationException


class TestNotificationContent:
    """NotificationContent値オブジェクトのテスト"""

    def test_create_follow_notification(self):
        """フォロー通知の作成テスト"""
        user_id = UserId(1)
        user_name = "testuser"

        content = NotificationContent.create_follow_notification(user_id, user_name)

        assert content.title == "新しいフォロワー"
        assert content.message == "testuserさんがあなたをフォローしました"
        assert content.actor_user_id == user_id
        assert content.actor_user_name == user_name
        assert content.related_post_id is None
        assert content.related_reply_id is None
        assert content.content_type is None

    def test_create_subscribe_notification(self):
        """サブスクライブ通知の作成テスト"""
        user_id = UserId(2)
        user_name = "subscriber"

        content = NotificationContent.create_subscribe_notification(user_id, user_name)

        assert content.title == "新しい購読者"
        assert content.message == "subscriberさんがあなたの投稿を購読しました"
        assert content.actor_user_id == user_id
        assert content.actor_user_name == user_name

    def test_create_like_notification_for_post(self):
        """ポストいいね通知の作成テスト"""
        liker_id = UserId(3)
        liker_name = "liker"
        content_type = "post"
        content_id = 100

        content = NotificationContent.create_like_notification(
            liker_id, liker_name, content_type, content_id
        )

        assert content.title == "いいね"
        assert content.message == "likerさんがあなたのpostにいいねしました"
        assert content.actor_user_id == liker_id
        assert content.actor_user_name == liker_name
        assert content.related_post_id == PostId(100)
        assert content.related_reply_id is None
        assert content.content_type == "post"

    def test_create_like_notification_for_reply(self):
        """リプライいいね通知の作成テスト"""
        liker_id = UserId(4)
        liker_name = "liker2"
        content_type = "reply"
        content_id = 200

        content = NotificationContent.create_like_notification(
            liker_id, liker_name, content_type, content_id
        )

        assert content.title == "いいね"
        assert content.message == "liker2さんがあなたのreplyにいいねしました"
        assert content.actor_user_id == liker_id
        assert content.related_post_id is None
        assert content.related_reply_id == ReplyId(200)
        assert content.content_type == "reply"

    def test_create_mention_notification_for_post(self):
        """ポストメンション通知の作成テスト"""
        mentioner_id = UserId(5)
        mentioner_name = "mentioner"
        content_type = "post"
        content_id = 300

        content = NotificationContent.create_mention_notification(
            mentioner_id, mentioner_name, content_type, content_id
        )

        assert content.title == "メンション"
        assert content.message == "mentionerさんがpostであなたをメンションしました"
        assert content.actor_user_id == mentioner_id
        assert content.related_post_id == PostId(300)
        assert content.related_reply_id is None
        assert content.content_type == "post"

    def test_create_reply_notification_for_post(self):
        """ポスト返信通知の作成テスト"""
        replier_id = UserId(6)
        replier_name = "replier"
        content_type = "post"
        content_id = 400

        content = NotificationContent.create_reply_notification(
            replier_id, replier_name, content_type, content_id
        )

        assert content.title == "新しい返信"
        assert content.message == "replierさんがあなたのpostに返信しました"
        assert content.actor_user_id == replier_id
        assert content.related_post_id == PostId(400)
        assert content.related_reply_id is None
        assert content.content_type == "post"

    def test_notification_content_immutability(self):
        """不変性のテスト"""
        user_id = UserId(7)
        content = NotificationContent.create_follow_notification(user_id, "user")

        # 属性を変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            content.title = "modified"

        with pytest.raises(AttributeError):
            content.message = "modified"

        with pytest.raises(AttributeError):
            content.actor_user_id = UserId(999)

        with pytest.raises(AttributeError):
            content.actor_user_name = "modified"

        with pytest.raises(AttributeError):
            content.related_post_id = PostId(999)

        with pytest.raises(AttributeError):
            content.related_reply_id = ReplyId(999)

        with pytest.raises(AttributeError):
            content.content_type = "modified"

    def test_invalid_content_type_like_notification(self):
        """いいね通知の無効なcontent_typeテスト"""
        liker_id = UserId(8)
        liker_name = "liker"

        with pytest.raises(NotificationContentValidationException, match="content_typeは「post」または「reply」である必要があります"):
            NotificationContent.create_like_notification(liker_id, liker_name, "invalid", 100)

    def test_invalid_content_type_mention_notification(self):
        """メンション通知の無効なcontent_typeテスト"""
        mentioner_id = UserId(9)
        mentioner_name = "mentioner"

        with pytest.raises(NotificationContentValidationException, match="content_typeは「post」または「reply」である必要があります"):
            NotificationContent.create_mention_notification(mentioner_id, mentioner_name, "invalid", 100)

    def test_invalid_content_type_reply_notification(self):
        """返信通知の無効なcontent_typeテスト"""
        replier_id = UserId(10)
        replier_name = "replier"

        with pytest.raises(NotificationContentValidationException, match="content_typeは「post」または「reply」である必要があります"):
            NotificationContent.create_reply_notification(replier_id, replier_name, "invalid", 100)

    def test_invalid_content_id_like_notification(self):
        """いいね通知の無効なcontent_idテスト"""
        liker_id = UserId(11)
        liker_name = "liker"

        with pytest.raises(NotificationContentValidationException, match="無効なcontent_idです"):
            NotificationContent.create_like_notification(liker_id, liker_name, "post", 0)

        with pytest.raises(NotificationContentValidationException, match="無効なcontent_idです"):
            NotificationContent.create_like_notification(liker_id, liker_name, "post", -1)

    def test_invalid_content_id_mention_notification(self):
        """メンション通知の無効なcontent_idテスト"""
        mentioner_id = UserId(12)
        mentioner_name = "mentioner"

        with pytest.raises(NotificationContentValidationException, match="無効なcontent_idです"):
            NotificationContent.create_mention_notification(mentioner_id, mentioner_name, "reply", 0)

    def test_invalid_content_id_reply_notification(self):
        """返信通知の無効なcontent_idテスト"""
        replier_id = UserId(13)
        replier_name = "replier"

        with pytest.raises(NotificationContentValidationException, match="無効なcontent_idです"):
            NotificationContent.create_reply_notification(replier_id, replier_name, "reply", -5)
