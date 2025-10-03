"""SnsEventHandlerRegistryのテスト"""

import pytest
from unittest.mock import Mock
from src.infrastructure.events.sns_event_handler_registry import SnsEventHandlerRegistry
from src.application.sns.services.notification_event_handler_service import NotificationEventHandlerService
from src.application.sns.services.relationship_event_handler_service import RelationshipEventHandlerService
from src.domain.sns.event import (
    SnsUserSubscribedEvent,
    SnsUserFollowedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
    SnsUserBlockedEvent,
)


class TestSnsEventHandlerRegistry:
    """SnsEventHandlerRegistryのテスト"""

    @pytest.fixture
    def mock_notification_handler(self):
        """テスト用の通知イベントハンドラーモック"""
        return Mock(spec=NotificationEventHandlerService)

    @pytest.fixture
    def mock_relationship_handler(self):
        """テスト用の関係イベントハンドラーモック"""
        return Mock(spec=RelationshipEventHandlerService)

    @pytest.fixture
    def registry(self, mock_notification_handler, mock_relationship_handler):
        """テスト用のSnsEventHandlerRegistry"""
        return SnsEventHandlerRegistry(
            notification_event_handler=mock_notification_handler,
            relationship_event_handler=mock_relationship_handler
        )

    @pytest.fixture
    def mock_event_publisher(self):
        """テスト用のEventPublisherモック"""
        return Mock()

    def test_register_handlers_registers_all_handlers(self, registry, mock_event_publisher):
        """全イベントハンドラが正しく登録されることをテスト"""
        registry.register_handlers(mock_event_publisher)

        # register_handlerが6回呼ばれることを確認（通知ハンドラ5つ + 関係ハンドラ1つ）
        assert mock_event_publisher.register_handler.call_count == 6

        # 各イベントタイプに対して正しいハンドラが登録されていることを確認
        calls = mock_event_publisher.register_handler.call_args_list

        # 各イベントタイプが登録されていることを確認
        registered_event_types = [call[0][0] for call in calls]
        expected_event_types = [
            SnsUserSubscribedEvent,
            SnsUserFollowedEvent,
            SnsPostCreatedEvent,
            SnsReplyCreatedEvent,
            SnsContentLikedEvent,
            SnsUserBlockedEvent,
        ]

        for expected_type in expected_event_types:
            assert expected_type in registered_event_types

    def test_event_handler_wrapper_calls_correct_method(self, registry, mock_notification_handler, mock_relationship_handler):
        """イベントハンドラのラッパーが正しいメソッドを呼ぶことをテスト"""
        mock_event_publisher = Mock()

        # ハンドラを登録
        registry.register_handlers(mock_event_publisher)

        # register_handlerの呼び出しからハンドラ関数を取得
        calls = mock_event_publisher.register_handler.call_args_list

        # SnsUserSubscribedEventのハンドラを取得
        subscribed_call = next(call for call in calls if call[0][0] == SnsUserSubscribedEvent)
        subscribed_handler = subscribed_call[0][1]

        # テストイベントを作成
        event = SnsUserSubscribedEvent.create(
            aggregate_id=Mock(),
            aggregate_type="UserAggregate",
            subscriber_user_id=Mock(),
            subscribed_user_id=Mock()
        )

        # ハンドラを実行
        subscribed_handler.handle(event)

        # 正しいメソッドが呼ばれたことを確認
        mock_notification_handler.handle_user_subscribed.assert_called_once_with(event)

    def test_relationship_handler_wrapper_calls_correct_method(self, registry, mock_notification_handler, mock_relationship_handler):
        """関係イベントハンドラのラッパーが正しいメソッドを呼ぶことをテスト"""
        mock_event_publisher = Mock()

        # ハンドラを登録
        registry.register_handlers(mock_event_publisher)

        # register_handlerの呼び出しからハンドラ関数を取得
        calls = mock_event_publisher.register_handler.call_args_list

        # SnsUserBlockedEventのハンドラを取得
        blocked_call = next(call for call in calls if call[0][0] == SnsUserBlockedEvent)
        blocked_handler = blocked_call[0][1]

        # テストイベントを作成
        event = SnsUserBlockedEvent.create(
            aggregate_id=Mock(),
            aggregate_type="UserAggregate",
            blocker_user_id=Mock(),
            blocked_user_id=Mock()
        )

        # ハンドラを実行
        blocked_handler.handle(event)

        # 正しいメソッドが呼ばれたことを確認
        mock_relationship_handler.handle_user_blocked.assert_called_once_with(event)
