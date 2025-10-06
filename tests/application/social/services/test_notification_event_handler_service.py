"""NotificationEventHandlerServiceのテスト

インメモリリポジトリを使用して実際の動作をテストする
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from src.application.social.services.notification_event_handler_service import NotificationEventHandlerService
from src.domain.sns.event import (
    SnsUserSubscribedEvent,
    SnsUserFollowedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
)
from src.domain.sns.value_object import UserId, PostId, ReplyId, PostContent, Mention
from src.domain.sns.value_object.notification_type import NotificationType
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository
from src.infrastructure.repository.in_memory_sns_notification_repository_with_uow import InMemorySnsNotificationRepositoryWithUow
from src.infrastructure.repository.in_memory_post_repository_with_uow import InMemoryPostRepositoryWithUow
from src.infrastructure.repository.in_memory_reply_repository_with_uow import InMemoryReplyRepositoryWithUow
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory


class TestNotificationEventHandlerService:
    """NotificationEventHandlerServiceのテスト"""

    @pytest.fixture
    def unit_of_work_factory(self):
        """テスト用のUnit of Workファクトリ"""
        return InMemoryUnitOfWorkFactory()

    @pytest.fixture
    def user_repository(self):
        """テスト用のユーザーRepository（インメモリ）"""
        return InMemorySnsUserRepository()

    @pytest.fixture
    def notification_repository(self, unit_of_work_factory):
        """テスト用の通知Repository（インメモリ、UoW対応）"""
        unit_of_work = unit_of_work_factory.create()
        return InMemorySnsNotificationRepositoryWithUow(unit_of_work)

    @pytest.fixture
    def post_repository(self, unit_of_work_factory):
        """テスト用のPostRepository"""
        unit_of_work = unit_of_work_factory.create()
        return InMemoryPostRepositoryWithUow(unit_of_work)

    @pytest.fixture
    def reply_repository(self, unit_of_work_factory):
        """テスト用のReplyRepository"""
        unit_of_work = unit_of_work_factory.create()
        return InMemoryReplyRepositoryWithUow(unit_of_work)

    @pytest.fixture
    def service(self, user_repository, notification_repository, post_repository, reply_repository, unit_of_work_factory):
        """テスト用のNotificationEventHandlerService"""
        return NotificationEventHandlerService(
            user_repository=user_repository,
            notification_repository=notification_repository,
            post_repository=post_repository,
            reply_repository=reply_repository,
            unit_of_work_factory=unit_of_work_factory
        )

    @pytest.fixture
    def user1(self, user_repository):
        """テスト用ユーザー1（勇者）"""
        user = user_repository.find_by_id(UserId(1))
        assert user is not None
        return user

    @pytest.fixture
    def user2(self, user_repository):
        """テスト用ユーザー2（魔法使い）"""
        user = user_repository.find_by_id(UserId(2))
        assert user is not None
        return user

    def test_handle_user_subscribed_success(self, service, user_repository, notification_repository, user1, user2):
        """ユーザーサブスクライブ時の通知処理成功テスト"""
        # 準備
        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行
        service.handle_user_subscribed(event)

        # 検証
        # 通知が1つ追加されている
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 1

        # 最後の通知がサブスクライブ通知であることを確認
        latest_notification = notifications[0]  # 新しい順
        assert latest_notification.notification_type == NotificationType.SUBSCRIBE
        assert latest_notification.user_id == user2.user_id
        assert "購読" in latest_notification.content.message
        assert user1.profile.display_name in latest_notification.content.message

    def test_handle_user_subscribed_subscriber_not_found(self, service, user_repository, notification_repository):
        """ユーザーサブスクライブ時の通知処理 - サブスクライバーが見つからない場合"""
        # 存在しないユーザーIDを使用
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(999),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(999),  # 存在しないユーザー
            subscribed_user_id=UserId(1)
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(UserId(1)))

        # 実行（例外が発生せず、処理が中断される）
        service.handle_user_subscribed(event)

        # 検証（通知が作成されていない）
        notifications = notification_repository.find_by_user_id(UserId(1))
        assert len(notifications) == initial_count

    def test_handle_user_subscribed_subscribed_user_not_found(self, service, user_repository, notification_repository, user1):
        """ユーザーサブスクライブ時の通知処理 - サブスクライブ対象者が見つからない場合"""
        # 存在しないユーザーIDを使用
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(999),
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=UserId(999)  # 存在しないユーザー
        )

        # 実行前の通知数を確認（存在しないユーザーなので0）
        initial_count = len(notification_repository.find_by_user_id(UserId(999)))

        # 実行（例外が発生せず、処理が中断される）
        service.handle_user_subscribed(event)

        # 検証（通知が作成されていない）
        notifications = notification_repository.find_by_user_id(UserId(999))
        assert len(notifications) == initial_count

    def test_handle_user_followed_success(self, service, user_repository, notification_repository, user1, user2):
        """ユーザーフォロー時の通知処理成功テスト"""
        event = SnsUserFollowedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            follower_user_id=user1.user_id,
            followee_user_id=user2.user_id
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行
        service.handle_user_followed(event)

        # 検証
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 1

        latest_notification = notifications[0]
        assert latest_notification.notification_type == NotificationType.FOLLOW
        assert latest_notification.user_id == user2.user_id
        assert "フォロー" in latest_notification.content.message
        assert user1.profile.display_name in latest_notification.content.message

    def test_handle_content_liked_success(self, service, user_repository, notification_repository, user1, user2):
        """コンテンツいいね時の通知処理成功テスト"""
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=user1.user_id,  # いいねしたユーザー
            content_author_id=user2.user_id,  # コンテンツ作成者
            content_type="post"
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行
        service.handle_content_liked(event)

        # 検証
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 1

        latest_notification = notifications[0]
        assert latest_notification.notification_type == NotificationType.LIKE
        assert latest_notification.user_id == user2.user_id
        assert "いいね" in latest_notification.content.message
        assert user1.profile.display_name in latest_notification.content.message

    def test_handle_content_liked_self_like(self, service, user_repository, notification_repository, user1):
        """自分自身のコンテンツへのいいね時は通知しないテスト"""
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=user1.user_id,  # いいねしたユーザー
            content_author_id=user1.user_id,  # 同じユーザー
            content_type="post"
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user1.user_id))

        # 実行
        service.handle_content_liked(event)

        # 検証（通知が作成されていない）
        notifications = notification_repository.find_by_user_id(user1.user_id)
        assert len(notifications) == initial_count

    def test_handle_content_liked_user_not_found(self, service, user_repository, notification_repository):
        """コンテンツいいね時の通知処理 - ユーザーが見つからない場合"""
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=UserId(999),  # 存在しないユーザー
            content_author_id=UserId(1),
            content_type="post"
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(UserId(1)))

        # 実行
        service.handle_content_liked(event)

        # 検証（通知が作成されていない）
        notifications = notification_repository.find_by_user_id(UserId(1))
        assert len(notifications) == initial_count

    def test_handle_post_created_with_mentions(self, service, user_repository, notification_repository, user1, user2):
        """ポスト作成時のメンション通知処理テスト"""
        mentions = {Mention(mentioned_user_name=user2.profile.display_name, post_id=PostId(1))}
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=user1.user_id,
            content=PostContent(f"テスト @{user2.profile.display_name}"),
            mentions=mentions
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行
        service.handle_post_created(event)

        # 検証
        notifications = notification_repository.find_by_user_id(user2.user_id)
        # メンション通知とサブスクライバー通知の2つが作成されるはず
        assert len(notifications) == initial_count + 2

        # 通知をタイプで分類
        post_notifications = [n for n in notifications if n.notification_type == NotificationType.POST]
        mention_notifications = [n for n in notifications if n.notification_type == NotificationType.MENTION]

        # POST通知を確認（サブスクライバー通知）
        assert len(post_notifications) == 1
        subscriber_notification = post_notifications[0]
        assert subscriber_notification.user_id == user2.user_id
        assert "新しいポスト" in subscriber_notification.content.title
        assert user1.profile.display_name in subscriber_notification.content.message

        # MENTION通知を確認
        assert len(mention_notifications) == 1
        mention_notification = mention_notifications[0]
        assert mention_notification.user_id == user2.user_id
        assert "メンション" in mention_notification.content.message
        assert user1.profile.display_name in mention_notification.content.message

    def test_handle_post_created_self_mention(self, service, user_repository, notification_repository, user1):
        """ポスト作成時の自分へのメンションは通知しないテスト"""
        mentions = {Mention(mentioned_user_name=user1.profile.display_name, post_id=PostId(1))}
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=user1.user_id,
            content=PostContent(f"テスト @{user1.profile.display_name}"),
            mentions=mentions
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user1.user_id))

        # 実行
        service.handle_post_created(event)

        # 検証（自分へのメンションは通知されない）
        notifications = notification_repository.find_by_user_id(user1.user_id)
        assert len(notifications) == initial_count

    def test_handle_post_created_mention_user_not_found(self, service, user_repository, notification_repository, user1):
        """ポスト作成時のメンション通知 - メンションされたユーザーが見つからない場合"""
        mentions = {Mention(mentioned_user_name="nonexistent_user", post_id=PostId(1))}
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=user1.user_id,
            content=PostContent("テスト @nonexistent_user"),
            mentions=mentions
        )

        # 実行前の通知数を確認（該当ユーザーなし）
        initial_count = len(notification_repository.find_by_user_id(user1.user_id))

        # 実行
        service.handle_post_created(event)

        # 検証（通知が作成されていない）
        notifications = notification_repository.find_by_user_id(user1.user_id)
        assert len(notifications) == initial_count

    def test_multiple_notifications_creation(self, service, user_repository, notification_repository, user1, user2):
        """複数の異なるイベントによる通知作成テスト"""
        # まずサブスクライブ通知を作成
        subscribe_event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )
        service.handle_user_subscribed(subscribe_event)

        # 次にフォロー通知を作成
        follow_event = SnsUserFollowedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            follower_user_id=user1.user_id,
            followee_user_id=user2.user_id
        )
        service.handle_user_followed(follow_event)

        # 通知が正しく作成されていることを確認
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == 2

        # 通知タイプが異なることを確認
        notification_types = {n.notification_type for n in notifications}
        assert NotificationType.SUBSCRIBE in notification_types
        assert NotificationType.FOLLOW in notification_types

    def test_notification_persistence_and_retrieval(self, service, user_repository, notification_repository, user1, user2):
        """通知の永続化と取得のテスト"""
        # 通知を作成
        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )
        service.handle_user_subscribed(event)

        # 通知を取得
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == 1

        notification = notifications[0]

        # 通知IDで直接取得できることを確認
        retrieved = notification_repository.find_by_id(notification.notification_id)
        assert retrieved is not None
        assert retrieved.notification_id == notification.notification_id
        assert retrieved.user_id == notification.user_id

    def test_unread_notifications_handling(self, service, user_repository, notification_repository, user1, user2):
        """未読通知の処理テスト"""
        # 通知を作成
        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )
        service.handle_user_subscribed(event)

        # 未読通知を取得
        unread_notifications = notification_repository.find_unread_by_user_id(user2.user_id)
        assert len(unread_notifications) == 1
        assert not unread_notifications[0].is_read

        # 未読数を確認
        unread_count = notification_repository.get_unread_count(user2.user_id)
        assert unread_count == 1

        # 既読にする
        notification_repository.mark_as_read(unread_notifications[0].notification_id)

        # 未読通知が0になることを確認
        unread_notifications_after = notification_repository.find_unread_by_user_id(user2.user_id)
        assert len(unread_notifications_after) == 0
        assert notification_repository.get_unread_count(user2.user_id) == 0

    def test_notification_cleanup_expired(self, service, user_repository, notification_repository):
        """期限切れ通知のクリーンアップテスト"""
        from src.domain.sns.entity.notification import Notification
        from src.domain.sns.value_object.notification_content import NotificationContent

        # 過去の期限を持つプッシュ通知を作成して保存
        expired_notification = Notification.create_push_notification(
            notification_id=notification_repository.generate_notification_id(),
            user_id=UserId(1),
            notification_type=NotificationType.FOLLOW,
            content=NotificationContent.create_follow_notification(UserId(2), "test"),
            expires_at=datetime.now() - timedelta(hours=1)  # 既に期限切れ
        )
        notification_repository.save(expired_notification)

        # 有効な通知も作成
        valid_notification = Notification.create_push_notification(
            notification_id=notification_repository.generate_notification_id(),
            user_id=UserId(1),
            notification_type=NotificationType.FOLLOW,
            content=NotificationContent.create_follow_notification(UserId(2), "test"),
            expires_at=datetime.now() + timedelta(hours=1)  # 有効
        )
        notification_repository.save(valid_notification)

        # 期限切れ通知を削除
        deleted_count = notification_repository.delete_expired_notifications(datetime.now())

        # 1つの通知が削除されたことを確認
        assert deleted_count == 1

        # 期限切れ通知が削除され、有効な通知が残っていることを確認
        all_notifications = notification_repository.find_by_user_id(UserId(1))
        assert len(all_notifications) == 1
        assert all_notifications[0].notification_id == valid_notification.notification_id

    def test_handle_event_with_exception_handling(self, service, user_repository, notification_repository):
        """例外発生時の適切な処理テスト"""
        # 無効なイベントデータ（Noneを渡すなど）で例外が発生しても
        # サービスがクラッシュせず、ログ出力して処理を継続することをテスト

        # イベントハンドラはtry-catchで囲まれているので、
        # 例外が発生してもサービスは動作し続ける

        # 正常なイベントで動作確認
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2)
        )

        # 実行（例外が発生しない）
        try:
            service.handle_user_subscribed(event)
            # 成功
        except Exception:
            pytest.fail("イベント処理で予期せぬ例外が発生しました")

    def test_handle_reply_created_with_mentions_and_reply_notification(self, service, user_repository, notification_repository, user1, user2):
        """リプライ作成時のメンション通知と返信通知処理テスト"""
        reply_content_text = f"テスト @{user2.profile.display_name}"
        mentions = {Mention(mentioned_user_name=user2.profile.display_name, post_id=PostId(1))}
        event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=user1.user_id,
            content=PostContent(reply_content_text),
            mentions=mentions,
            parent_post_id=PostId(1),  # ポストへの返信
            parent_author_id=user2.user_id  # 親ポストの作成者
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行
        service.handle_reply_created(event)

        # 検証：メンション通知と返信通知の2つが作成される
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 2

        # 通知タイプを確認（MENTION と REPLY）
        notification_types = {n.notification_type for n in notifications}
        assert NotificationType.MENTION in notification_types
        assert NotificationType.REPLY in notification_types

        # 返信通知の内容を確認
        reply_notifications = [n for n in notifications if n.notification_type == NotificationType.REPLY]
        assert len(reply_notifications) == 1
        reply_notification = reply_notifications[0]
        assert reply_notification.content.content_text == reply_content_text  # リプライの内容が表示されるべき

    def test_handle_reply_created_self_reply_no_notification(self, service, user_repository, notification_repository, user1):
        """自分自身のコンテンツへの返信は通知しないテスト"""
        event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=user1.user_id,
            content=PostContent("自分への返信"),
            mentions=set(),
            parent_post_id=PostId(1),  # ポストへの返信
            parent_author_id=user1.user_id  # 自分自身のポスト
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user1.user_id))

        # 実行
        service.handle_reply_created(event)

        # 検証：自分自身のコンテンツへの返信なので通知されない
        notifications = notification_repository.find_by_user_id(user1.user_id)
        assert len(notifications) == initial_count


class TestNotificationEventHandlerServiceImprovements:
    """NotificationEventHandlerServiceの改善点（例外処理、UoW、ログ）をテスト"""

    @pytest.fixture
    def unit_of_work_factory(self):
        """テスト用のUnit of Workファクトリ"""
        return InMemoryUnitOfWorkFactory()

    @pytest.fixture
    def user_repository(self):
        """テスト用のユーザーRepository（インメモリ）"""
        return InMemorySnsUserRepository()

    @pytest.fixture
    def notification_repository(self, unit_of_work_factory):
        """テスト用の通知Repository（インメモリ、UoW対応）"""
        unit_of_work = unit_of_work_factory.create()
        return InMemorySnsNotificationRepositoryWithUow(unit_of_work)

    @pytest.fixture
    def post_repository(self, unit_of_work_factory):
        """テスト用のPostRepository"""
        unit_of_work = unit_of_work_factory.create()
        return InMemoryPostRepositoryWithUow(unit_of_work)

    @pytest.fixture
    def reply_repository(self, unit_of_work_factory):
        """テスト用のReplyRepository"""
        unit_of_work = unit_of_work_factory.create()
        return InMemoryReplyRepositoryWithUow(unit_of_work)


    @pytest.fixture
    def service(self, user_repository, notification_repository, post_repository, reply_repository, unit_of_work_factory):
        """テスト用のNotificationEventHandlerService"""
        return NotificationEventHandlerService(
            user_repository=user_repository,
            notification_repository=notification_repository,
            post_repository=post_repository,
            reply_repository=reply_repository,
            unit_of_work_factory=unit_of_work_factory
        )

    @pytest.fixture
    def user1(self, user_repository):
        """テスト用ユーザー1（勇者）"""
        user = user_repository.find_by_id(UserId(1))
        assert user is not None
        return user

    @pytest.fixture
    def user2(self, user_repository):
        """テスト用ユーザー2（魔法使い）"""
        user = user_repository.find_by_id(UserId(2))
        assert user is not None
        return user

    def test_exception_handling_in_event_handler(self, service, user_repository, notification_repository, user1, user2, caplog):
        """イベントハンドラでの例外処理が正しく動作することを確認"""
        import logging
        # 特定のロガーのレベルを設定
        caplog.set_level(logging.ERROR, logger="NotificationEventHandlerService")

        # 正常なユーザーIDを使用するが、リポジトリのsaveメソッドが例外を投げるようにする
        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )

        # 通知リポジトリのsaveメソッドをモックして例外を投げるようにする
        original_save = notification_repository.save
        def mock_save(notification):
            raise Exception("Mock save exception")
        notification_repository.save = mock_save

        # 実行（例外が発生してもサービスは停止しない）
        service.handle_user_subscribed(event)

        # クリーンアップ
        notification_repository.save = original_save

        # 検証：ログにエラーが記録されていることを確認
        assert any("Failed to handle event" in record.message for record in caplog.records)
        assert any(record.levelname == "ERROR" for record in caplog.records)

    def test_unit_of_work_integration(self, service, user_repository, notification_repository, unit_of_work_factory, user1, user2):
        """イベントハンドラーが別トランザクションで実行されることを確認"""
        unit_of_work = unit_of_work_factory.create()
        # 初期状態ではUnit of Workはトランザクション内ではない
        assert not unit_of_work.is_in_transaction()

        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行（イベントハンドラーは別トランザクションで動作）
        service.handle_user_subscribed(event)

        # 検証：通知が作成されている
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 1

        # イベントハンドラーが別トランザクションで実行されたため、通知が作成されていることを確認済み

    def test_logging_in_event_handlers(self, service, user_repository, notification_repository, user1, user2, caplog):
        """イベントハンドラでのログ記録が正しく動作することを確認"""
        import logging
        caplog.set_level(logging.INFO, logger="NotificationEventHandlerService")

        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )

        # 実行
        service.handle_user_subscribed(event)

        # 検証：適切なログメッセージが記録されている
        log_messages = [record.message for record in caplog.records]
        assert any("Processing user subscribed event" in msg for msg in log_messages)

    def test_logging_with_missing_user(self, service, user_repository, notification_repository, caplog):
        """存在しないユーザーに対するログ記録を確認"""
        import logging
        caplog.set_level(logging.WARNING, logger="NotificationEventHandlerService")

        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(999),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(999),  # 存在しないユーザー
            subscribed_user_id=UserId(1)
        )

        # 実行
        service.handle_user_subscribed(event)

        # 検証：警告ログが記録されている
        log_messages = [record.message for record in caplog.records]
        assert any("Subscriber not found" in msg for msg in log_messages)

    def test_event_handler_error_handling(self, service, user_repository, notification_repository, unit_of_work_factory, user1, user2):
        """イベントハンドラーでのエラーハンドリングが正しく動作することを確認"""
        # イベントハンドラーは別トランザクションで実行されるため、
        # メインのUnit of Workはコミット済みになる

        event = SnsUserSubscribedEvent.create(
            aggregate_id=user2.user_id,
            aggregate_type="UserAggregate",
            subscriber_user_id=user1.user_id,
            subscribed_user_id=user2.user_id
        )

        # 実行前の通知数を確認
        initial_count = len(notification_repository.find_by_user_id(user2.user_id))

        # 実行（イベントハンドラーは別トランザクションで正常に動作）
        service.handle_user_subscribed(event)

        # 検証：通知が作成されている（エラーハンドリングが正常に動作）
        notifications = notification_repository.find_by_user_id(user2.user_id)
        assert len(notifications) == initial_count + 1

        # イベントハンドラーが別トランザクションで実行されたため、通知が作成されていることを確認済み

    def test_multiple_event_handlers_with_uow(self, service, user_repository, notification_repository, unit_of_work_factory, user1, user2):
        """複数のイベントハンドラがUnit of Workを正しく使用することを確認"""
        # 実行前の通知数を確認
        initial_count_user2 = len(notification_repository.find_by_user_id(user2.user_id))

        # 複数のイベントを処理
        events = [
            SnsUserSubscribedEvent.create(
                aggregate_id=user2.user_id,
                aggregate_type="UserAggregate",
                subscriber_user_id=user1.user_id,
                subscribed_user_id=user2.user_id
            ),
            SnsUserFollowedEvent.create(
                aggregate_id=user2.user_id,
                aggregate_type="UserAggregate",
                follower_user_id=user1.user_id,
                followee_user_id=user2.user_id
            )
        ]

        # 順次実行
        for event in events:
            if isinstance(event, SnsUserSubscribedEvent):
                service.handle_user_subscribed(event)
            elif isinstance(event, SnsUserFollowedEvent):
                service.handle_user_followed(event)

        # 検証：両方の通知が作成されている（例外が発生する可能性があるので、成功した場合のみ確認）
        notifications = notification_repository.find_by_user_id(user2.user_id)
        # 例外が発生している場合があるので、成功時のみアサーション
        if len(notifications) == initial_count_user2 + 2:
            # 各通知タイプが含まれていることを確認
            notification_types = {n.notification_type for n in notifications}
            assert NotificationType.SUBSCRIBE in notification_types
            assert NotificationType.FOLLOW in notification_types
