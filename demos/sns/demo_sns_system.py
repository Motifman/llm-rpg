#!/usr/bin/env python3
"""
SNSシステム総合デモ

このデモでは、UserQueryServiceを使ってプロフィール確認機能を実装し、
UserCommandServiceを使ってユーザーの関係を更新したり、新しいユーザーを追加したりする機能を実装しています。
さらに、PostQueryServiceを使ってポストの表示機能を実装しています。
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
"""

import sys
import os
from typing import Optional

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.domain.sns.value_object import UserId
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
from src.application.sns.services.user_query_service import UserQueryService
from src.application.sns.services.user_command_service import UserCommandService
from src.application.sns.services.post_query_service import PostQueryService
from src.application.sns.contracts.dtos import UserProfileDto, PostDto
from src.application.sns.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand
)
from src.application.sns.exceptions import UserQueryException, UserCommandException
from src.application.sns.exceptions.query.post_query_exception import PostQueryException


class SnsDemo:
    """SNSシステム総合デモ"""

    def __init__(self):
        """初期化"""
        self.repository = InMemorySnsUserRepository()
        self.post_repository = InMemoryPostRepository()
        self.user_query_service = UserQueryService(self.repository)
        self.post_query_service = PostQueryService(self.post_repository, self.repository)
        self.event_publisher = InMemoryEventPublisher()
        self.user_command_service = UserCommandService(self.repository, self.event_publisher)

        # デフォルトのログイン状態（勇者としてログイン）
        self.current_user_id: int = 1
        self.current_user_name: str = "勇者"

        # メインメニューオプション
        self.main_menu_options = {
            '1': ('ユーザー関係の表示・更新', self.show_user_relationships_menu),
            '2': ('ポストの表示', self.show_posts_menu),
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

        # ポスト表示サブメニュー
        self.post_menu_options = {
            '1': ('自分のタイムライン表示', self.show_my_timeline),
            '2': ('他のユーザーのタイムライン表示', self.show_user_timeline),
            '3': ('ホームタイムライン表示', self.show_home_timeline),
            '4': ('個別のポスト表示', self.show_single_post),
            '5': ('自分のプライベートポスト表示', self.show_private_posts),
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
        """ポスト表示サブメニューを表示"""
        while True:
            self.display_header()
            self.display_menu(self.post_menu_options, "ポスト表示メニュー")

            choice = self.get_user_input("ポスト表示メニューを選択してください: ", list(self.post_menu_options.keys()))

            # 選択された機能を呼び出し
            action_name, action_func = self.post_menu_options[choice]
            print(f"\n🔄 {action_name}を実行中...")

            action_func()

            # メインメニューに戻る場合は終了
            if choice == '0':
                break

            # 次の操作を促す
            input("\n⏎  Enterキーを押してポスト表示メニューに戻る...")

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
    demo = SnsDemo()
    demo.run()


if __name__ == "__main__":
    main()
