#!/usr/bin/env python3
"""
SNSシステム総合デモ

このデモでは、UserQueryServiceを使ってプロフィール確認機能を実装し、
UserCommandServiceを使ってユーザーの関係を更新したり、新しいユーザーを追加したりする機能を実装しています。
さらに、PostQueryServiceを使ってポストの表示機能を実装しています。
また、ReplyQueryServiceとReplyCommandServiceを使ってリプライの管理機能を実装しています。
サンプルデータの中の一人のユーザーとしてログインしている状態をシミュレーションします。

機能:
【プロフィール確認機能 (UserQueryService)】
- 自分のプロフィール表示
- 他のユーザーのプロフィール表示
- フォロー中ユーザーの一覧表示
- フォロワーの一覧表示
- ブロック中ユーザーの一覧表示
- ブロックしているユーザーの一覧表示
- 購読中ユーザーの一覧表示
- 購読者の一覧表示

【ユーザー管理機能 (UserCommandService)】
- 新しいユーザーを作成
- 自分のプロフィールを更新
- ユーザーをフォロー/フォロー解除
- ユーザーをブロック/ブロック解除
- ユーザーを購読/購読解除

【ポスト表示機能 (PostQueryService)】
- 自分のタイムライン表示
- 他のユーザーのタイムライン表示
- ホームタイムライン表示（フォロー中のユーザーのポスト）
- 個別のポスト表示
- 自分のプライベートポスト表示
- 自分がいいねしたポスト一覧表示
- ハッシュタグでポストを検索
- キーワードでポストを検索
- 人気ポストの表示
- トレンドハッシュタグの表示

【ポスト管理機能 (PostCommandService)】
- 新しいポストを作成（公開範囲設定）
- ポストにいいね
- ポストを削除

【リプライ表示機能 (ReplyQueryService)】
- ポストとリプライのツリー構造を取得
- 個別のリプライを取得
- ユーザーのリプライ一覧を取得

【リプライ管理機能 (ReplyCommandService)】
- ポストにリプライを行う
- リプライにリプライを行う
- リプライにいいね
- リプライを削除

【通知表示機能 (NotificationQueryService)】
- 自分の通知一覧を表示
- 未読通知を表示
- 未読通知数を表示

【通知管理機能 (NotificationCommandService)】
- 通知を既読にする
- 全通知を既読にする

【イベントハンドラ機能】
- フォロー時の通知自動生成
- サブスクライブ時の通知自動生成
- ポスト作成時の通知自動生成（メンション・サブスクライバー向け）
- リプライ作成時の通知自動生成（メンション・返信向け）
- いいね時の通知自動生成
- ブロック時の関係自動解除
"""

import sys
import os
from typing import Optional

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.domain.sns.value_object import UserId
from src.infrastructure.repository.in_memory_sns_user_repository_with_uow import InMemorySnsUserRepositoryWithUow
from src.infrastructure.repository.in_memory_post_repository_with_uow import InMemoryPostRepositoryWithUow
from src.infrastructure.repository.in_memory_reply_repository_with_uow import InMemoryReplyRepositoryWithUow
from src.infrastructure.repository.in_memory_sns_notification_repository_with_uow import InMemorySnsNotificationRepositoryWithUow
from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow
from src.infrastructure.events.sns_event_handler_registry import SnsEventHandlerRegistry
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.infrastructure.di.container import DependencyInjectionContainer
from src.application.social.services.user_query_service import UserQueryService
from src.application.social.services.user_command_service import UserCommandService
from src.application.social.services.post_query_service import PostQueryService
from src.application.social.services.post_command_service import PostCommandService
from src.application.social.services.reply_query_service import ReplyQueryService
from src.application.social.services.reply_command_service import ReplyCommandService
from src.application.social.services.notification_query_service import NotificationQueryService
from src.application.social.services.notification_command_service import NotificationCommandService
from src.application.social.services.notification_event_handler_service import NotificationEventHandlerService
from src.application.social.services.relationship_event_handler_service import RelationshipEventHandlerService
from src.application.social.contracts.dtos import UserProfileDto, PostDto, ReplyDto, ReplyThreadDto, NotificationDto
from src.application.social.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand,
    CreatePostCommand,
    LikePostCommand,
    DeletePostCommand,
    CreateReplyCommand,
    LikeReplyCommand,
    DeleteReplyCommand,
    MarkNotificationAsReadCommand,
    MarkAllNotificationsAsReadCommand
)
from src.application.social.exceptions import UserQueryException, UserCommandException
from src.application.social.exceptions.query.post_query_exception import PostQueryException
from src.application.social.exceptions.command.post_command_exception import PostCommandException
from src.application.social.exceptions.query.reply_query_exception import ReplyQueryException
from src.application.social.exceptions.command.reply_command_exception import ReplyCommandException
from src.domain.sns.enum import PostVisibility


class SnsDemo:
    """SNSシステム総合デモ"""

    def __init__(self):
        """初期化"""
        # 依存性注入コンテナを作成
        container = DependencyInjectionContainer()

        # Unit of Workファクトリを取得
        unit_of_work_factory = container.get_unit_of_work_factory()

        # Unit of Workとイベントパブリッシャーを取得
        self.unit_of_work, self.event_publisher = container.get_unit_of_work_and_publisher()

        # Unit of Work対応版のリポジトリを作成
        self.repository = InMemorySnsUserRepositoryWithUow(self.unit_of_work)
        self.post_repository = InMemoryPostRepositoryWithUow(self.unit_of_work)
        self.reply_repository = InMemoryReplyRepositoryWithUow(self.unit_of_work)
        self.notification_repository = InMemorySnsNotificationRepositoryWithUow(self.unit_of_work)

        # サービスを作成
        self.user_query_service = UserQueryService(self.repository)
        self.post_query_service = PostQueryService(self.post_repository, self.repository)
        self.reply_query_service = ReplyQueryService(self.post_repository, self.repository, self.reply_repository)
        self.notification_query_service = NotificationQueryService(self.notification_repository)
        self.user_command_service = UserCommandService(self.repository, self.event_publisher, self.unit_of_work)
        self.post_command_service = PostCommandService(self.post_repository, self.repository, self.event_publisher, self.unit_of_work)
        self.reply_command_service = ReplyCommandService(self.post_repository, self.repository, self.reply_repository, self.event_publisher, self.unit_of_work)
        self.notification_command_service = NotificationCommandService(self.notification_repository, self.unit_of_work)

        # イベントハンドラを作成（ファクトリインスタンスを使用）
        self.notification_event_handler = NotificationEventHandlerService(
            self.repository, self.notification_repository, self.post_repository, self.reply_repository, unit_of_work_factory
        )
        self.relationship_event_handler = RelationshipEventHandlerService(self.repository, unit_of_work_factory)

        # イベントハンドラをイベントパブリッシャーに登録
        event_handler_registry = SnsEventHandlerRegistry(
            self.notification_event_handler,
            self.relationship_event_handler
        )
        event_handler_registry.register_handlers(self.event_publisher)

        # デフォルトのログイン状態（勇者としてログイン）
        self.current_user_id: int = 1
        self.current_user_name: str = "勇者"

        # メインメニューオプション
        self.main_menu_options = {
            '1': ('ユーザー関係の表示・更新', self.show_user_relationships_menu),
            '2': ('ポストの表示', self.show_posts_menu),
            '3': ('リプライの表示・管理', self.show_replies_menu),
            '4': ('通知の表示・管理', self.show_notifications_menu),
            '0': ('終了', self.exit_demo),
        }

        # ユーザー関係サブメニュー
        self.user_menu_options = {
            '1': ('自分のプロフィール表示', self.show_my_profile),
            '2': ('他のユーザーのプロフィール表示', self.show_other_user_profile),
            '3': ('フォロー中ユーザーの一覧', self.show_followees),
            '4': ('フォロワーの一覧', self.show_followers),
            '5': ('ブロック中ユーザーの一覧', self.show_blocked_users),
            '6': ('ブロックしているユーザーの一覧', self.show_blockers),
            '7': ('購読中ユーザーの一覧', self.show_subscriptions),
            '8': ('購読者の一覧', self.show_subscribers),
            '9': ('ログイン状態の変更', self.change_login_user),
            'A': ('新しいユーザーを作成', self.create_new_user),
            'B': ('自分のプロフィールを更新', self.update_my_profile),
            'C': ('ユーザーをフォロー', self.follow_user),
            'D': ('ユーザーのフォローを解除', self.unfollow_user),
            'E': ('ユーザーをブロック', self.block_user),
            'F': ('ユーザーのブロックを解除', self.unblock_user),
            'G': ('ユーザーを購読', self.subscribe_user),
            'H': ('ユーザーの購読を解除', self.unsubscribe_user),
            '0': ('メインメニューに戻る', self.back_to_main_menu),
        }

        # ポスト表示・管理サブメニュー
        self.post_menu_options = {
            '1': ('自分のタイムライン表示', self.show_my_timeline),
            '2': ('他のユーザーのタイムライン表示', self.show_user_timeline),
            '3': ('ホームタイムライン表示', self.show_home_timeline),
            '4': ('個別のポスト表示', self.show_single_post),
            '5': ('自分のプライベートポスト表示', self.show_private_posts),
            '6': ('自分がいいねしたポスト一覧', self.show_liked_posts),
            '7': ('ハッシュタグでポストを検索', self.search_posts_by_hashtag),
            '8': ('キーワードでポストを検索', self.search_posts_by_keyword),
            '9': ('人気ポストを表示', self.show_popular_posts),
            '10': ('トレンドハッシュタグを表示', self.show_trending_hashtags),
            '11': ('新しいポストを作成', self.create_new_post),
            '12': ('ポストにいいね', self.like_post),
            '13': ('ポストを削除', self.delete_post),
            '0': ('メインメニューに戻る', self.back_to_main_menu),
        }

        # リプライ表示・管理サブメニュー
        self.reply_menu_options = {
            '1': ('ポストにリプライを行う', self.reply_to_post),
            '2': ('リプライにリプライを行う', self.reply_to_reply),
            '3': ('リプライにいいね', self.like_reply),
            '4': ('リプライを削除', self.delete_reply),
            '5': ('ポストとリプライのツリー構造を取得', self.get_reply_thread),
            '6': ('個別のリプライを取得', self.get_single_reply),
            '7': ('ユーザーのリプライ一覧を取得', self.get_user_replies),
            '0': ('メインメニューに戻る', self.back_to_main_menu),
        }

        # 通知表示・管理サブメニュー
        self.notification_menu_options = {
            '1': ('自分の通知一覧を表示', self.show_my_notifications),
            '2': ('未読通知を表示', self.show_unread_notifications),
            '3': ('未読通知数を表示', self.show_unread_count),
            '4': ('通知を既読にする', self.mark_notification_as_read),
            '5': ('全通知を既読にする', self.mark_all_notifications_as_read),
            '0': ('メインメニューに戻る', self.back_to_main_menu),
        }

    def display_header(self):
        """ヘッダーを表示"""
        print("=" * 60)
        print("🔍 SNSシステム総合デモ")
        print(f"👤 現在のログイン: {self.current_user_name} (ID: {self.current_user_id})")
        print("=" * 60)

    def display_menu(self, menu_options, menu_title="メニュー"):
        """メニューを表示"""
        print(f"\n📋 {menu_title}:")
        for key, (description, _) in menu_options.items():
            if key == '0':
                print(f"  {key}. {description}")
            elif key.isdigit():
                print(f"  {key}. {description}")
            else:
                print(f"  {key}. {description}")
        print()

    def show_user_relationships_menu(self):
        """ユーザー関係の表示・更新サブメニューを表示"""
        while True:
            self.display_header()
            self.display_menu(self.user_menu_options, "ユーザー関係メニュー")

            choice = self.get_user_input("ユーザー関係メニューを選択してください: ", list(self.user_menu_options.keys()))

            # 選択された機能を呼び出し
            action_name, action_func = self.user_menu_options[choice]
            print(f"\n🔄 {action_name}を実行中...")

            action_func()

            # メインメニューに戻る場合は終了
            if choice == '0':
                break

            # 次の操作を促す
            input("\n⏎  Enterキーを押してユーザー関係メニューに戻る...")

    def show_posts_menu(self):
        """ポスト表示・管理サブメニューを表示"""
        while True:
            self.display_header()
            self.display_menu(self.post_menu_options, "ポスト表示・管理メニュー")

            choice = self.get_user_input("ポスト表示・管理メニューを選択してください: ", list(self.post_menu_options.keys()))

            # 選択された機能を呼び出し
            action_name, action_func = self.post_menu_options[choice]
            print(f"\n🔄 {action_name}を実行中...")

            action_func()

            # メインメニューに戻る場合は終了
            if choice == '0':
                break

            # 次の操作を促す
            input("\n⏎  Enterキーを押してポスト表示・管理メニューに戻る...")

    def show_replies_menu(self):
        """リプライ表示・管理サブメニューを表示"""
        while True:
            self.display_header()
            self.display_menu(self.reply_menu_options, "リプライ表示・管理メニュー")

            choice = self.get_user_input("リプライ表示・管理メニューを選択してください: ", list(self.reply_menu_options.keys()))

            # 選択された機能を呼び出し
            action_name, action_func = self.reply_menu_options[choice]
            print(f"\n🔄 {action_name}を実行中...")

            action_func()

            # メインメニューに戻る場合は終了
            if choice == '0':
                break

            # 次の操作を促す
            input("\n⏎  Enterキーを押してリプライ表示・管理メニューに戻る...")

    def show_notifications_menu(self):
        """通知表示・管理サブメニューを表示"""
        while True:
            self.display_header()
            self.display_menu(self.notification_menu_options, "通知表示・管理メニュー")

            choice = self.get_user_input("通知表示・管理メニューを選択してください: ", list(self.notification_menu_options.keys()))

            # 選択された機能を呼び出し
            action_name, action_func = self.notification_menu_options[choice]
            print(f"\n🔄 {action_name}を実行中...")

            action_func()

            # メインメニューに戻る場合は終了
            if choice == '0':
                break

            # 次の操作を促す
            input("\n⏎  Enterキーを押して通知表示・管理メニューに戻る...")

    def back_to_main_menu(self):
        """メインメニューに戻る（何もしない）"""
        pass

    def get_user_input(self, prompt: str, valid_options: Optional[list] = None) -> str:
        """ユーザー入力取得"""
        while True:
            try:
                user_input = input(prompt).strip()
                if valid_options and user_input not in valid_options:
                    print(f"⚠️  無効なオプションです。{valid_options}から選択してください。")
                    continue
                return user_input
            except KeyboardInterrupt:
                print("\n\n🛑 終了します...")
                self.exit_demo()
            except EOFError:
                # コマンドライン実行時は自動的に終了
                print("\n\n💻 コマンドライン実行のため終了します...")
                self.exit_demo()

    def show_my_profile(self):
        """自分のプロフィール表示"""
        print("\n👤 自分のプロフィール:")
        print("-" * 40)

        try:
            profile = self.user_query_service.show_my_profile(self.current_user_id)

            self.display_profile_info(profile, is_self=True)

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_other_user_profile(self):
        """他のユーザーのプロフィール表示"""
        print("\n👥 他のユーザーのプロフィール:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            if user.user_id != self.current_user_id:
                profile_info = user.get_user_profile_info()
                print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        # ユーザー選択
        try:
            target_id_str = self.get_user_input("表示するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("⚠️  自分自身のプロフィールはメニュー1から表示してください。")
                return

            profile = self.user_query_service.show_other_user_profile(target_id, self.current_user_id)
            self.display_profile_info(profile, is_self=False)

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_followees(self):
        """フォロー中ユーザーの一覧表示"""
        print(f"\n👥 {self.current_user_name}のフォロー中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_followees_profile(self.current_user_id)
            self.display_profile_list(profiles, "フォロー中ユーザー")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_followers(self):
        """フォロワーの一覧表示"""
        print(f"\n👥 {self.current_user_name}のフォロワー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_followers_profile(self.current_user_id)
            self.display_profile_list(profiles, "フォロワー")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_blocked_users(self):
        """ブロック中ユーザーの一覧表示"""
        print(f"\n🚫 {self.current_user_name}のブロック中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_blocked_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "ブロック中ユーザー")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_blockers(self):
        """ブロックしているユーザーの一覧表示"""
        print(f"\n🚫 {self.current_user_name}をブロックしているユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_blockers_profile(self.current_user_id)
            self.display_profile_list(profiles, "ブロックしているユーザー")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_subscriptions(self):
        """購読中ユーザーの一覧表示"""
        print(f"\n📖 {self.current_user_name}の購読中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_subscriptions_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "購読中ユーザー")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_subscribers(self):
        """購読者の一覧表示"""
        print(f"\n📖 {self.current_user_name}の購読者:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_subscribers_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "購読者")

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def change_login_user(self):
        """ログイン状態の変更"""
        print("\n🔄 ログイン状態の変更:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            profile_info = user.get_user_profile_info()
            marker = "👤" if user.user_id == self.current_user_id else "  "
            print(f"  {marker} ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        # ユーザー選択
        try:
            new_user_id_str = self.get_user_input("新しいユーザーIDを入力: ")
            new_user_id = int(new_user_id_str)

            # ユーザー情報を取得
            user = self.repository.find_by_id(UserId(new_user_id))
            if user is None:
                print(f"❌ ユーザーID {new_user_id} は存在しません。")
                return

            profile_info = user.get_user_profile_info()
            self.current_user_id = new_user_id
            self.current_user_name = profile_info['display_name']

            print(f"✅ ログイン状態を変更しました: {self.current_user_name} (ID: {self.current_user_id})")

        except ValueError:
            print("❌ 数値を入力してください。")
        except Exception as e:
            print(f"❌ エラー: {str(e)}")

    def display_profile_info(self, profile: UserProfileDto, is_self: bool):
        """プロフィール情報を表示"""
        print(f"ID: {profile.user_id}")
        print(f"ユーザー名: {profile.user_name}")
        print(f"表示名: {profile.display_name}")
        print(f"自己紹介: {profile.bio}")
        print(f"フォロー数: {profile.followee_count}")
        print(f"フォロワー数: {profile.follower_count}")

        if not is_self:
            print("\n関係性:")
            if profile.is_following:
                print("     フォロー中")
            if profile.is_followed_by:
                print("     フォローされています")
            if profile.is_blocked:
                print("     ブロック中")
            if profile.is_blocked_by:
                print("     ブロックされています")
            if profile.is_subscribed:
                print("     購読中")
            if profile.is_subscribed_by:
                print("     購読されています")

    def display_post_info(self, post: PostDto):
        """ポスト情報を表示"""
        visibility_emoji = {
            "public": "🌐",
            "followers_only": "👥",
            "private": "🔒"
        }.get(post.visibility, "❓")

        print(f"📝 ポストID: {post.post_id}")
        print(f"👤 投稿者: {post.author_display_name} (@{post.author_user_name})")
        print(f"📅 投稿日時: {post.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"👁️ 可視性: {visibility_emoji} {post.visibility}")
        print(f"💬 内容: {post.content}")

        if post.hashtags:
            hashtags_str = " ".join(f"#{tag}" for tag in post.hashtags)
            print(f"🏷️ ハッシュタグ: {hashtags_str}")

        print(f"👍 いいね数: {post.like_count}")
        print(f"💬 リプライ数: {post.reply_count}")

        # 自分の反応状態
        reactions = []
        if post.is_liked_by_viewer:
            reactions.append("いいね済み")
        if post.is_replied_by_viewer:
            reactions.append("リプライ済み")
        if reactions:
            print(f"✨ 自分の反応: {'、'.join(reactions)}")

        if post.mentioned_users:
            mentions_str = " ".join(f"@{user}" for user in post.mentioned_users)
            print(f"📢 メンション: {mentions_str}")

        if post.is_deleted:
            print("🗑️ このポストは削除されています")

        print("-" * 50)

    def display_reply_info(self, reply: ReplyDto):
        """リプライ情報を表示"""
        visibility_emoji = {
            "public": "🌐",
            "followers_only": "👥",
            "private": "🔒"
        }.get(reply.visibility, "❓")

        # 深さに応じてインデント
        indent = "  " * reply.depth

        print(f"{indent}💬 リプライID: {reply.reply_id}")
        print(f"{indent}👤 投稿者: {reply.author_display_name} (@{reply.author_user_name})")
        print(f"{indent}📅 投稿日時: {reply.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{indent}👁️ 可視性: {visibility_emoji} {reply.visibility}")
        print(f"{indent}💬 内容: {reply.content}")

        if reply.hashtags:
            hashtags_str = " ".join(f"#{tag}" for tag in reply.hashtags)
            print(f"{indent}🏷️ ハッシュタグ: {hashtags_str}")

        print(f"{indent}👍 いいね数: {reply.like_count}")

        # 自分の反応状態
        reactions = []
        if reply.is_liked_by_viewer:
            reactions.append("いいね済み")
        if reactions:
            print(f"{indent}✨ 自分の反応: {'、'.join(reactions)}")

        if reply.mentioned_users:
            mentions_str = " ".join(f"@{user}" for user in reply.mentioned_users)
            print(f"{indent}📢 メンション: {mentions_str}")

        if reply.is_deleted:
            print(f"{indent}🗑️ このリプライは削除されています")

        print(f"{indent}" + "-" * 40)

    def display_post_list(self, posts: list[PostDto], title: str):
        """ポスト一覧を表示"""
        if not posts:
            print(f"📝 {title}は存在しません。")
            return

        print(f"📝 {title} ({len(posts)}件):")
        print("=" * 60)

        for i, post in enumerate(posts, 1):
            print(f"\n{i}. ", end="")
            self.display_post_info(post)

    def display_reply_list(self, replies: list[ReplyDto], title: str):
        """リプライ一覧を表示"""
        if not replies:
            print(f"💬 {title}は存在しません。")
            return

        print(f"💬 {title} ({len(replies)}件):")
        print("=" * 60)

        for i, reply in enumerate(replies, 1):
            print(f"\n{i}. ", end="")
            self.display_reply_info(reply)

    def display_notification_info(self, notification: NotificationDto):
        """通知情報を表示"""
        type_emojis = {
            "follow": "👥",
            "subscribe": "📖",
            "post": "📝",
            "reply": "💬",
            "mention": "@",
            "like": "👍"
        }

        type_names = {
            "follow": "フォロー",
            "subscribe": "購読",
            "post": "新規投稿",
            "reply": "返信",
            "mention": "メンション",
            "like": "いいね"
        }

        emoji = type_emojis.get(notification.notification_type, "🔔")
        type_name = type_names.get(notification.notification_type, notification.notification_type)

        print(f"{emoji} {type_name}通知")
        print(f"   通知ID: {notification.notification_id}")
        print(f"   タイトル: {notification.title}")
        print(f"   メッセージ: {notification.message}")
        print(f"   アクター: {notification.actor_user_name} (ID: {notification.actor_user_id})")
        print(f"   作成日時: {notification.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   既読: {'はい' if notification.is_read else 'いいえ'}")

        # 通知タイプ別の追加情報
        if notification.notification_type in ["like", "mention", "reply"]:
            if notification.content_type:
                content_type_ja = "ポスト" if notification.content_type == "post" else "リプライ"
                content_id = notification.related_post_id if notification.content_type == "post" else notification.related_reply_id
                print(f"   対象コンテンツ: {content_type_ja} (ID: {content_id})")
                if notification.content_text:
                    # 内容を50文字以内に制限
                    content_preview = notification.content_text[:50] + "..." if len(notification.content_text) > 50 else notification.content_text
                    print(f"   コンテンツ内容: {content_preview}")

        elif notification.notification_type == "post":
            if notification.content_text:
                # 内容を50文字以内に制限
                content_preview = notification.content_text[:50] + "..." if len(notification.content_text) > 50 else notification.content_text
                print(f"   投稿内容: {content_preview}")

        if notification.expires_at:
            print(f"   有効期限: {notification.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")

        print("-" * 60)

    def display_notification_list(self, notifications: list[NotificationDto], title: str):
        """通知一覧を表示"""
        if not notifications:
            print(f"🔔 {title}は存在しません。")
            return

        print(f"🔔 {title} ({len(notifications)}件):")
        print("=" * 60)

        for i, notification in enumerate(notifications, 1):
            print(f"\n{i}. ", end="")
            self.display_notification_info(notification)

    def display_profile_list(self, profiles: list[UserProfileDto], title: str):
        """プロフィール一覧を表示"""
        if not profiles:
            print(f"📝 {title}は存在しません。")
            return

        print(f"📝 {title} ({len(profiles)}人):")
        for i, profile in enumerate(profiles, 1):
            print(f"\n  {i}. {profile.display_name} (@{profile.user_name})")
            print(f"     ID: {profile.user_id}")
            print(f"     自己紹介: {profile.bio}")
            print(f"     フォロー数: {profile.followee_count}, フォロワー数: {profile.follower_count}")

            # 関係性情報（自分以外のユーザーに対して）
            if profile.user_id != self.current_user_id:
                if profile.is_following:
                    print("     フォロー中")
                if profile.is_followed_by:
                    print("     フォローされています")
                if profile.is_blocked:
                    print("     ブロック中")
                if profile.is_blocked_by:
                    print("     ブロックされています")
                if profile.is_subscribed:
                    print("     購読中")
                if profile.is_subscribed_by:
                    print("     購読されています")

    def create_new_user(self):
        """新しいユーザーを作成"""
        print("\n👤 新しいユーザー作成:")
        print("-" * 40)

        try:
            # ユーザー情報の入力
            user_name = self.get_user_input("ユーザー名を入力: ").strip()
            if not user_name:
                print("❌ ユーザー名は必須です。")
                return

            display_name = self.get_user_input("表示名を入力: ").strip()
            if not display_name:
                print("❌ 表示名は必須です。")
                return

            bio = self.get_user_input("自己紹介を入力 (空欄可): ").strip()

            # コマンド実行
            command = CreateUserCommand(
                user_name=user_name,
                display_name=display_name,
                bio=bio
            )

            result = self.user_command_service.create_user(command)

            print(f"✅ ユーザーが正常に作成されました！")
            print(f"   ユーザーID: {result.data['user_id']}")
            print(f"   ユーザー名: {user_name}")
            print(f"   表示名: {display_name}")

        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def update_my_profile(self):
        """自分のプロフィールを更新"""
        print(f"\n👤 {self.current_user_name}のプロフィール更新:")
        print("-" * 40)

        try:
            # 現在のプロフィールを取得して表示
            current_profile = self.user_query_service.show_my_profile(self.current_user_id)
            print("現在のプロフィール:")
            print(f"  表示名: {current_profile.display_name}")
            print(f"  自己紹介: {current_profile.bio}")
            print()

            # 更新情報の入力
            new_display_name = self.get_user_input(f"新しい表示名 (現在の: {current_profile.display_name}, 空欄で変更なし): ").strip()
            new_bio = self.get_user_input(f"新しい自己紹介 (現在の: {current_profile.bio}, 空欄で変更なし): ").strip()

            # 変更がない場合はスキップ
            if not new_display_name and not new_bio:
                print("ℹ️ 変更がないため、更新をスキップします。")
                return

            # コマンド実行
            command = UpdateUserProfileCommand(
                user_id=self.current_user_id,
                new_display_name=new_display_name if new_display_name else None,
                new_bio=new_bio if new_bio else None
            )

            result = self.user_command_service.update_user_profile(command)

            print("✅ プロフィールが正常に更新されました！")
            if new_display_name:
                self.current_user_name = new_display_name
                print(f"   新しい表示名: {new_display_name}")
            if new_bio:
                print(f"   新しい自己紹介: {new_bio}")

        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def follow_user(self):
        """ユーザーをフォロー"""
        print(f"\n👥 {self.current_user_name}がユーザーをフォロー:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            if user.user_id != self.current_user_id:
                profile_info = user.get_user_profile_info()
                print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        try:
            target_id_str = self.get_user_input("フォローするユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身をフォローすることはできません。")
                return

            # コマンド実行
            command = FollowUserCommand(
                follower_user_id=self.current_user_id,
                followee_user_id=target_id
            )

            result = self.user_command_service.follow_user(command)

            print(f"✅ ユーザーをフォローしました！")
            print(f"   フォロワー: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   フォロー対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def unfollow_user(self):
        """ユーザーのフォローを解除"""
        print(f"\n👥 {self.current_user_name}がユーザーのフォローを解除:")
        print("-" * 40)

        try:
            target_id_str = self.get_user_input("フォロー解除するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身のフォローを解除することはできません。")
                return

            # コマンド実行
            command = UnfollowUserCommand(
                follower_user_id=self.current_user_id,
                followee_user_id=target_id
            )

            result = self.user_command_service.unfollow_user(command)

            print(f"✅ ユーザーのフォローを解除しました！")
            print(f"   フォロワー: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   フォロー解除対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def block_user(self):
        """ユーザーをブロック"""
        print(f"\n🚫 {self.current_user_name}がユーザーをブロック:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            if user.user_id != self.current_user_id:
                profile_info = user.get_user_profile_info()
                print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        try:
            target_id_str = self.get_user_input("ブロックするユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身をブロックすることはできません。")
                return

            # コマンド実行
            command = BlockUserCommand(
                blocker_user_id=self.current_user_id,
                blocked_user_id=target_id
            )

            result = self.user_command_service.block_user(command)

            print(f"✅ ユーザーをブロックしました！")
            print(f"   ブロッカー: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   ブロック対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def unblock_user(self):
        """ユーザーのブロックを解除"""
        print(f"\n🚫 {self.current_user_name}がユーザーのブロックを解除:")
        print("-" * 40)

        try:
            target_id_str = self.get_user_input("ブロック解除するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身のブロックを解除することはできません。")
                return

            # コマンド実行
            command = UnblockUserCommand(
                blocker_user_id=self.current_user_id,
                blocked_user_id=target_id
            )

            result = self.user_command_service.unblock_user(command)

            print(f"✅ ユーザーのブロックを解除しました！")
            print(f"   ブロッカー: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   ブロック解除対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def subscribe_user(self):
        """ユーザーを購読"""
        print(f"\n📖 {self.current_user_name}がユーザーを購読:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            if user.user_id != self.current_user_id:
                profile_info = user.get_user_profile_info()
                print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        try:
            target_id_str = self.get_user_input("購読するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身を購読することはできません。")
                return

            # コマンド実行
            command = SubscribeUserCommand(
                subscriber_user_id=self.current_user_id,
                subscribed_user_id=target_id
            )

            result = self.user_command_service.subscribe_user(command)

            print(f"✅ ユーザーを購読しました！")
            print(f"   購読者: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   購読対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def unsubscribe_user(self):
        """ユーザーの購読を解除"""
        print(f"\n📖 {self.current_user_name}がユーザーの購読を解除:")
        print("-" * 40)

        try:
            target_id_str = self.get_user_input("購読解除するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("❌ 自分自身の購読を解除することはできません。")
                return

            # コマンド実行
            command = UnsubscribeUserCommand(
                subscriber_user_id=self.current_user_id,
                subscribed_user_id=target_id
            )

            result = self.user_command_service.unsubscribe_user(command)

            print(f"✅ ユーザーの購読を解除しました！")
            print(f"   購読者: {self.current_user_name} (ID: {self.current_user_id})")
            print(f"   購読解除対象: ID {target_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except UserCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_my_timeline(self):
        """自分のタイムライン表示"""
        print(f"\n📝 {self.current_user_name}のタイムライン:")
        print("-" * 40)

        try:
            posts = self.post_query_service.get_user_timeline(self.current_user_id, self.current_user_id)
            self.display_post_list(posts, f"{self.current_user_name}のタイムライン")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_user_timeline(self):
        """他のユーザーのタイムライン表示"""
        print("\n📝 他のユーザーのタイムライン:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            profile_info = user.get_user_profile_info()
            print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        try:
            target_id_str = self.get_user_input("タイムラインを表示するユーザーIDを入力: ")
            target_id = int(target_id_str)

            if target_id == self.current_user_id:
                print("⚠️  自分のタイムラインはメニュー1から表示してください。")
                return

            posts = self.post_query_service.get_user_timeline(target_id, self.current_user_id)
            user_name = "不明なユーザー"
            # ユーザー名を取得
            user = self.repository.find_by_id(UserId(target_id))
            if user:
                user_name = user.get_user_profile_info()['display_name']

            self.display_post_list(posts, f"{user_name}のタイムライン")

        except ValueError:
            print("❌ 数値を入力してください。")
        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_home_timeline(self):
        """ホームタイムライン表示（フォロー中のユーザーのポスト）"""
        print(f"\n🏠 {self.current_user_name}のホームタイムライン:")
        print("-" * 40)

        try:
            posts = self.post_query_service.get_home_timeline(self.current_user_id)
            self.display_post_list(posts, f"{self.current_user_name}のホームタイムライン")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_single_post(self):
        """個別のポスト表示"""
        print("\n📝 個別のポスト表示:")
        print("-" * 40)

        try:
            post_id_str = self.get_user_input("表示するポストIDを入力: ")
            post_id = int(post_id_str)

            post = self.post_query_service.get_post(post_id, self.current_user_id)

            if post:
                print(f"📝 ポスト詳細:")
                print("=" * 60)
                self.display_post_info(post)
            else:
                print("❌ 指定されたポストが見つかりません。")

        except ValueError:
            print("❌ 数値を入力してください。")
        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_private_posts(self):
        """自分のプライベートポスト表示"""
        print(f"\n🔒 {self.current_user_name}のプライベートポスト:")
        print("-" * 40)

        try:
            posts = self.post_query_service.get_private_posts(self.current_user_id)
            self.display_post_list(posts, f"{self.current_user_name}のプライベートポスト")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_liked_posts(self):
        """自分がいいねしたポスト一覧表示"""
        print(f"\n👍 {self.current_user_name}がいいねしたポスト:")
        print("-" * 40)

        try:
            posts = self.post_query_service.get_liked_posts(self.current_user_id, self.current_user_id)
            self.display_post_list(posts, f"{self.current_user_name}がいいねしたポスト")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def search_posts_by_hashtag(self):
        """ハッシュタグでポストを検索"""
        print("\n🏷️ ハッシュタグでポストを検索:")
        print("-" * 40)

        try:
            hashtag = self.get_user_input("検索するハッシュタグを入力 (#は不要): ").strip()
            if not hashtag:
                print("❌ ハッシュタグは必須です。")
                return

            posts = self.post_query_service.search_posts_by_hashtag(hashtag, self.current_user_id)
            self.display_post_list(posts, f"ハッシュタグ「#{hashtag}」の検索結果")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def search_posts_by_keyword(self):
        """キーワードでポストを検索"""
        print("\n🔍 キーワードでポストを検索:")
        print("-" * 40)

        try:
            keyword = self.get_user_input("検索キーワードを入力: ").strip()
            if not keyword:
                print("❌ キーワードは必須です。")
                return

            posts = self.post_query_service.search_posts_by_keyword(keyword, self.current_user_id)
            self.display_post_list(posts, f"キーワード「{keyword}」の検索結果")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_popular_posts(self):
        """人気ポストを表示"""
        print("\n🔥 人気ポストランキング:")
        print("-" * 40)

        try:
            posts = self.post_query_service.get_popular_posts(self.current_user_id)
            self.display_post_list(posts, "人気ポストランキング")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_trending_hashtags(self):
        """トレンドハッシュタグを表示"""
        print("\n📈 トレンドハッシュタグ:")
        print("-" * 40)

        try:
            hashtags = self.post_query_service.get_trending_hashtags()
            if not hashtags:
                print("📝 トレンドハッシュタグが見つかりません。")
                return

            print(f"📝 トレンドハッシュタグ ({len(hashtags)}件):")
            print("=" * 60)

            for i, hashtag in enumerate(hashtags, 1):
                print(f"  {i}. {hashtag}")

        except PostQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def create_new_post(self):
        """新しいポストを作成"""
        print(f"\n📝 {self.current_user_name}が新しいポストを作成:")
        print("-" * 40)

        try:
            # ポスト内容の入力
            content = self.get_user_input("ポスト内容を入力: ").strip()
            if not content:
                print("❌ ポスト内容は必須です。")
                return

            # 可視性の選択
            visibility_options = {
                '1': ('公開 (public)', PostVisibility.PUBLIC),
                '2': ('フォロワー限定 (followers_only)', PostVisibility.FOLLOWERS_ONLY),
                '3': ('プライベート (private)', PostVisibility.PRIVATE),
            }

            print("\n可視性を選択してください:")
            for key, (description, _) in visibility_options.items():
                print(f"  {key}. {description}")

            visibility_choice = self.get_user_input("可視性選択: ", list(visibility_options.keys()))
            _, visibility = visibility_options[visibility_choice]

            # コマンド実行
            command = CreatePostCommand(
                user_id=self.current_user_id,
                content=content,
                visibility=visibility
            )

            result = self.post_command_service.create_post(command)

            print("✅ ポストが正常に作成されました！")
            print(f"   ポストID: {result.data['post_id']}")
            print(f"   内容: {content}")
            print(f"   可視性: {visibility.value}")

        except PostCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def like_post(self):
        """ポストにいいね"""
        print(f"\n👍 {self.current_user_name}がポストにいいね:")
        print("-" * 40)

        try:
            # いいねするポストIDの入力
            post_id_str = self.get_user_input("いいねするポストIDを入力: ")
            post_id = int(post_id_str)

            # コマンド実行
            command = LikePostCommand(
                post_id=post_id,
                user_id=self.current_user_id
            )

            result = self.post_command_service.like_post(command)

            print("✅ ポストにいいねしました！")
            print(f"   ポストID: {post_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except PostCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def delete_post(self):
        """ポストを削除"""
        print(f"\n🗑️ {self.current_user_name}がポストを削除:")
        print("-" * 40)

        try:
            # 削除するポストIDの入力
            post_id_str = self.get_user_input("削除するポストIDを入力: ")
            post_id = int(post_id_str)

            # コマンド実行
            command = DeletePostCommand(
                post_id=post_id,
                user_id=self.current_user_id
            )

            result = self.post_command_service.delete_post(command)

            print("✅ ポストが正常に削除されました！")
            print(f"   ポストID: {post_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except PostCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def reply_to_post(self):
        """ポストにリプライを行う"""
        print(f"\n💬 {self.current_user_name}がポストにリプライを行う:")
        print("-" * 40)

        try:
            # 利用可能なポストを表示
            all_posts = self.post_repository.find_all()
            if not all_posts:
                print("📝 ポストが存在しません。")
                return

            print("利用可能なポスト:")
            for i, post in enumerate(all_posts, 1):
                # 投稿者情報を取得
                author_user = self.repository.find_by_id(post.author_user_id)
                author_display_name = "不明なユーザー"
                if author_user:
                    author_display_name = author_user.get_user_profile_info()['display_name']

                content_preview = post.content.content[:50] + "..." if len(post.content.content) > 50 else post.content.content
                print(f"  {i}. ID: {post.post_id}, 投稿者: {author_display_name}, 内容: {content_preview}")

            # ポスト選択
            post_choice_str = self.get_user_input("リプライするポスト番号を入力: ")
            post_choice = int(post_choice_str) - 1

            if post_choice < 0 or post_choice >= len(all_posts):
                print("❌ 無効なポスト番号です。")
                return

            selected_post = all_posts[post_choice]

            # リプライ内容の入力
            content = self.get_user_input("リプライ内容を入力: ").strip()
            if not content:
                print("❌ リプライ内容は必須です。")
                return

            # 可視性の選択
            visibility_options = {
                '1': ('公開 (public)', PostVisibility.PUBLIC),
                '2': ('フォロワー限定 (followers_only)', PostVisibility.FOLLOWERS_ONLY),
                '3': ('プライベート (private)', PostVisibility.PRIVATE),
            }

            print("\n可視性を選択してください:")
            for key, (description, _) in visibility_options.items():
                print(f"  {key}. {description}")

            visibility_choice = self.get_user_input("可視性選択: ", list(visibility_options.keys()))
            _, visibility = visibility_options[visibility_choice]

            # コマンド実行
            command = CreateReplyCommand(
                user_id=self.current_user_id,
                content=content,
                visibility=visibility,
                parent_post_id=selected_post.post_id.value
            )

            result = self.reply_command_service.create_reply(command)

            print("✅ リプライが正常に作成されました！")
            print(f"   リプライID: {result.data['reply_id']}")
            print(f"   ポストID: {selected_post.post_id.value}")
            print(f"   内容: {content}")
            print(f"   可視性: {visibility.value}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def reply_to_reply(self):
        """リプライにリプライを行う"""
        print(f"\n💬 {self.current_user_name}がリプライにリプライを行う:")
        print("-" * 40)

        try:
            # 利用可能なリプライを表示（ツリー構造で表示）
            print("利用可能なリプライ:")
            print("ツリー構造で表示します...")

            # 全てのポストに対してツリーを取得してリプライを表示
            all_posts = self.post_repository.find_all()
            if not all_posts:
                print("📝 ポストが存在しません。")
                return

            reply_options = []
            reply_count = 0

            for post in all_posts:
                try:
                    # 各ポストのリプライツリーを取得
                    reply_thread = self.reply_query_service.get_reply_thread(post.post_id.value, self.current_user_id)

                    if reply_thread.replies:
                        # ポスト情報を表示
                        print(f"\n📝 ポストID: {post.post_id.value}")
                        self.display_post_info(reply_thread.post)

                        # リプライツリーを表示（番号付き）
                        for reply in reply_thread.replies:
                            reply_count += 1
                            reply_options.append(reply)
                            # リプライ番号を表示（インデント付き）
                            indent = "  " * reply.depth
                            print(f"{indent}{reply_count}. ", end="")
                            self.display_reply_info(reply)
                except Exception:
                    # ポストにリプライがない場合はスキップ
                    continue

            if not reply_options:
                print("💬 リプライが存在しません。")
                return

            # リプライ選択
            reply_choice_str = self.get_user_input("リプライするリプライ番号を入力: ")
            reply_choice = int(reply_choice_str) - 1

            if reply_choice < 0 or reply_choice >= len(reply_options):
                print("❌ 無効なリプライ番号です。")
                return

            selected_reply = reply_options[reply_choice]

            # リプライ内容の入力
            content = self.get_user_input("リプライ内容を入力: ").strip()
            if not content:
                print("❌ リプライ内容は必須です。")
                return

            # 可視性の選択
            visibility_options = {
                '1': ('公開 (public)', PostVisibility.PUBLIC),
                '2': ('フォロワー限定 (followers_only)', PostVisibility.FOLLOWERS_ONLY),
                '3': ('プライベート (private)', PostVisibility.PRIVATE),
            }

            print("\n可視性を選択してください:")
            for key, (description, _) in visibility_options.items():
                print(f"  {key}. {description}")

            visibility_choice = self.get_user_input("可視性選択: ", list(visibility_options.keys()))
            _, visibility = visibility_options[visibility_choice]

            # コマンド実行
            command = CreateReplyCommand(
                user_id=self.current_user_id,
                content=content,
                visibility=visibility,
                parent_reply_id=selected_reply.reply_id
            )

            result = self.reply_command_service.create_reply(command)

            print("✅ リプライが正常に作成されました！")
            print(f"   リプライID: {result.data['reply_id']}")
            print(f"   親リプライID: {selected_reply.reply_id}")
            print(f"   内容: {content}")
            print(f"   可視性: {visibility.value}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def like_reply(self):
        """リプライにいいね"""
        print(f"\n👍 {self.current_user_name}がリプライにいいね:")
        print("-" * 40)

        try:
            # いいねするリプライIDの入力
            reply_id_str = self.get_user_input("いいねするリプライIDを入力: ")
            reply_id = int(reply_id_str)

            # コマンド実行
            command = LikeReplyCommand(
                reply_id=reply_id,
                user_id=self.current_user_id
            )

            result = self.reply_command_service.like_reply(command)

            print("✅ リプライにいいねしました！")
            print(f"   リプライID: {reply_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def delete_reply(self):
        """リプライを削除"""
        print(f"\n🗑️ {self.current_user_name}がリプライを削除:")
        print("-" * 40)

        try:
            # 削除するリプライIDの入力
            reply_id_str = self.get_user_input("削除するリプライIDを入力: ")
            reply_id = int(reply_id_str)

            # コマンド実行
            command = DeleteReplyCommand(
                reply_id=reply_id,
                user_id=self.current_user_id
            )

            result = self.reply_command_service.delete_reply(command)

            print("✅ リプライが正常に削除されました！")
            print(f"   リプライID: {reply_id}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyCommandException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def get_reply_thread(self):
        """ポストとリプライのツリー構造を取得"""
        print("\n🌳 ポストとリプライのツリー構造を取得:")
        print("-" * 40)

        try:
            # ポストIDの入力
            post_id_str = self.get_user_input("ツリーを表示するポストIDを入力: ")
            post_id = int(post_id_str)

            # リプライツリーを取得
            reply_thread = self.reply_query_service.get_reply_thread(post_id, self.current_user_id)

            # ポストを表示
            print(f"📝 ポスト:")
            print("=" * 60)
            self.display_post_info(reply_thread.post)

            # リプライツリーを表示
            if reply_thread.replies:
                print(f"\n💬 リプライツリー ({len(reply_thread.replies)}件):")
                print("=" * 60)
                for reply in reply_thread.replies:
                    self.display_reply_info(reply)
            else:
                print("\n💬 このポストにはリプライがありません。")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def get_single_reply(self):
        """個別のリプライを取得"""
        print("\n💬 個別のリプライを取得:")
        print("-" * 40)

        try:
            # リプライIDの入力
            reply_id_str = self.get_user_input("表示するリプライIDを入力: ")
            reply_id = int(reply_id_str)

            # リプライを取得
            reply = self.reply_query_service.get_reply_by_id(reply_id, self.current_user_id)

            if reply:
                print(f"💬 リプライ詳細:")
                print("=" * 60)
                self.display_reply_info(reply)
            else:
                print("❌ 指定されたリプライが見つかりません。")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def get_user_replies(self):
        """ユーザーのリプライ一覧を取得"""
        print("\n💬 ユーザーのリプライ一覧を取得:")
        print("-" * 40)

        # 利用可能なユーザーを表示
        all_users = self.repository.find_all()
        print("利用可能なユーザー:")
        for user in all_users:
            profile_info = user.get_user_profile_info()
            print(f"  ID: {user.user_id}, 名前: {profile_info['user_name']}, 表示名: {profile_info['display_name']}")

        try:
            # ユーザーIDの入力
            user_id_str = self.get_user_input("リプライ一覧を表示するユーザーIDを入力: ")
            user_id = int(user_id_str)

            # リプライ一覧を取得
            replies = self.reply_query_service.get_user_replies(user_id, self.current_user_id)

            # ユーザー名を取得
            user = self.repository.find_by_id(UserId(user_id))
            user_name = "不明なユーザー"
            if user:
                user_name = user.get_user_profile_info()['display_name']

            self.display_reply_list(replies, f"{user_name}のリプライ一覧")

        except ValueError:
            print("❌ 数値を入力してください。")
        except ReplyQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_my_notifications(self):
        """自分の通知一覧を表示"""
        print(f"\n🔔 {self.current_user_name}の通知一覧:")
        print("-" * 40)

        try:
            notifications = self.notification_query_service.get_user_notifications(self.current_user_id)
            self.display_notification_list(notifications, f"{self.current_user_name}の通知一覧")

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_unread_notifications(self):
        """未読通知を表示"""
        print(f"\n🔔 {self.current_user_name}の未読通知:")
        print("-" * 40)

        try:
            notifications = self.notification_query_service.get_unread_notifications(self.current_user_id)
            self.display_notification_list(notifications, f"{self.current_user_name}の未読通知")

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def show_unread_count(self):
        """未読通知数を表示"""
        print(f"\n🔔 {self.current_user_name}の未読通知数:")
        print("-" * 40)

        try:
            count = self.notification_query_service.get_unread_count(self.current_user_id)
            print(f"未読通知数: {count}件")

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def mark_notification_as_read(self):
        """通知を既読にする"""
        print(f"\n🔔 {self.current_user_name}が通知を既読にする:")
        print("-" * 40)

        try:
            # 未読通知を表示して選択
            unread_notifications = self.notification_query_service.get_unread_notifications(self.current_user_id)
            if not unread_notifications:
                print("未読通知はありません。")
                return

            print("未読通知:")
            for i, notification in enumerate(unread_notifications, 1):
                # 通知タイプ別の簡易表示
                type_emojis = {
                    "follow": "👥",
                    "subscribe": "📖",
                    "post": "📝",
                    "reply": "💬",
                    "mention": "@",
                    "like": "👍"
                }
                emoji = type_emojis.get(notification.notification_type, "🔔")

                # 簡易メッセージを作成
                if notification.notification_type in ["like", "mention", "reply"]:
                    content_info = f" ({notification.content_type})" if notification.content_type else ""
                    preview = f" - {notification.content_text[:30]}..." if notification.content_text and len(notification.content_text) > 30 else ""
                    print(f"  {i}. {emoji} {notification.title}: {notification.actor_user_name}{content_info}{preview}")
                elif notification.notification_type == "post":
                    preview = f" - {notification.content_text[:30]}..." if notification.content_text and len(notification.content_text) > 30 else ""
                    print(f"  {i}. {emoji} {notification.title}: {notification.actor_user_name}{preview}")
                else:
                    print(f"  {i}. {emoji} {notification.title}: {notification.actor_user_name}")

            # 通知選択
            choice_str = self.get_user_input("既読にする通知番号を入力: ")
            choice = int(choice_str) - 1

            if choice < 0 or choice >= len(unread_notifications):
                print("❌ 無効な通知番号です。")
                return

            selected_notification = unread_notifications[choice]

            # コマンド実行
            command = MarkNotificationAsReadCommand(
                notification_id=selected_notification.notification_id
            )

            result = self.notification_command_service.mark_notification_as_read(command)

            if result.success:
                print("✅ 通知を既読にしました！")
            else:
                print(f"❌ エラー: {result.message}")

        except ValueError:
            print("❌ 数値を入力してください。")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def mark_all_notifications_as_read(self):
        """全通知を既読にする"""
        print(f"\n🔔 {self.current_user_name}が全通知を既読にする:")
        print("-" * 40)

        try:
            # 確認
            confirm = self.get_user_input("本当に全ての通知を既読にしますか？ (y/N): ").lower()
            if confirm != 'y':
                print("キャンセルしました。")
                return

            # コマンド実行
            command = MarkAllNotificationsAsReadCommand(
                user_id=self.current_user_id
            )

            result = self.notification_command_service.mark_all_notifications_as_read(command)

            if result.success:
                print("✅ 全通知を既読にしました！")
            else:
                print(f"❌ エラー: {result.message}")

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def exit_demo(self):
        """デモ終了"""
        print("\n👋 SNSシステム総合デモを終了します。")
        sys.exit(0)

    def run(self):
        """メインメソッド"""
        print("🌟 SNSシステム総合デモ")
        print("このデモでは、UserQueryServiceとUserCommandServiceを使って")
        print("プロフィールの確認とユーザー関係の管理機能を実装しています。")
        print("さらに、PostQueryServiceを使ってポストの表示機能を実装しています。")
        print("また、PostCommandServiceを使ってポストの作成・いいね・削除機能を")
        print("実装しています。")
        print("さらに、ReplyQueryServiceとReplyCommandServiceを使ってリプライの")
        print("作成・リプライへの返信・いいね・削除・ツリー表示・個別表示・一覧表示機能を")
        print("実装しています。")
        print("さらに、NotificationQueryServiceとNotificationCommandServiceを使って通知の")
        print("表示・既読化機能を、イベントハンドラを使って自動通知生成機能を")
        print("実装しています。")
        print("また、ユーザーをブロックした際の関係解除処理も確認できます。")
        print("サンプルデータの中の一人のユーザーとしてログインしている状態をシミュレーションします。\n")

        try:
            while True:
                self.display_header()
                self.display_menu(self.main_menu_options, "メインメニュー")

                choice = self.get_user_input("メニューを選択してください: ", list(self.main_menu_options.keys()))

                # 選択された機能を呼び出し
                action_name, action_func = self.main_menu_options[choice]
                print(f"\n🔄 {action_name}を実行中...")

                action_func()

                # 次の操作を促す（終了以外）
                if choice != '0':
                    input("\n⏎  Enterキーを押してメインメニューに戻る...")

        except KeyboardInterrupt:
            self.exit_demo()


def main():
    """メイン関数"""
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='sns_demo_debug.log'
    )
    demo = SnsDemo()
    demo.run()


if __name__ == "__main__":
    main()
