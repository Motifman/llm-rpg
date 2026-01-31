#!/usr/bin/env python3
"""
フォロー機能修正テストスクリプト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.events.sns_event_handler_registry import SnsEventHandlerRegistry
from ai_rpg_world.application.sns.services.user_command_service import UserCommandService
from ai_rpg_world.application.sns.services.notification_event_handler_service import NotificationEventHandlerService
from ai_rpg_world.application.sns.services.relationship_event_handler_service import RelationshipEventHandlerService
from ai_rpg_world.application.sns.contracts.commands import FollowUserCommand
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile


def test_follow_functionality():
    """フォロー機能のテスト"""
    print("🔧 フォロー機能修正テスト開始")

    # Unit of Workファクトリ関数を定義（別トランザクション用）
    def create_uow():
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

    # Unit of Workとイベントパブリッシャーを作成
    unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
        unit_of_work_factory=create_uow
    )

    # リポジトリを作成
    user_repository = InMemorySnsUserRepository()
    notification_repository = InMemorySnsNotificationRepository()
    post_repository = InMemoryPostRepository()
    reply_repository = InMemoryReplyRepository()

    # イベントハンドラーを登録
    notification_handler = NotificationEventHandlerService(
        user_repository=user_repository,
        notification_repository=notification_repository,
        post_repository=post_repository,
        reply_repository=reply_repository,
        unit_of_work_factory=create_uow
    )

    relationship_handler = RelationshipEventHandlerService(
        user_repository=user_repository,
        unit_of_work_factory=create_uow
    )

    # イベントハンドラーレジストリを使用して登録
    registry = SnsEventHandlerRegistry(
        notification_event_handler=notification_handler,
        relationship_event_handler=relationship_handler
    )
    registry.register_handlers(event_publisher)

    # コマンドサービスを作成
    user_command_service = UserCommandService(
        user_repository=user_repository,
        event_publisher=event_publisher,
        unit_of_work=unit_of_work
    )

    # テストユーザーを作成
    from ai_rpg_world.domain.sns.value_object.user_id import UserId

    hero_user = UserAggregate.create_new_user(
        user_id=UserId(1),
        user_name="hero_user",
        display_name="勇者",
        bio="勇者です"
    )

    thief_user = UserAggregate.create_new_user(
        user_id=UserId(4),
        user_name="thief_user",
        display_name="盗賊",
        bio="盗賊です"
    )

    # ユーザーを保存
    user_repository.save(hero_user)
    user_repository.save(thief_user)

    print(f"✅ テストユーザー作成完了: {hero_user.profile.display_name}, {thief_user.profile.display_name}")

    # フォローコマンド実行
    print("🔗 盗賊が勇者をフォロー実行...")
    command = FollowUserCommand(
        follower_user_id=4,  # 盗賊
        followee_user_id=1   # 勇者
    )

    try:
        # フォロー処理を実行（コマンドサービスが内部でUnit of Workを管理）
        result = user_command_service.follow_user(command)
        print("✅ フォロー成功！")
        print(f"   結果: {result}")

        # 通知が作成されたか確認
        notifications = notification_repository.find_by_user_id(UserId(1))  # 勇者の通知
        print(f"✅ 通知作成確認: {len(notifications)}件の通知が作成されました")

        if notifications:
            notification = notifications[0]
            print(f"   通知内容: {notification.content.message}")
        else:
            print("⚠️ 通知が作成されていません")

    except Exception as e:
        print(f"❌ エラー発生: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    print("🎉 フォロー機能修正テスト完了")
    return True


if __name__ == "__main__":
    success = test_follow_functionality()
    sys.exit(0 if success else 1)
