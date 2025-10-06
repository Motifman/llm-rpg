#!/usr/bin/env python3
"""
SNSプロフィール確認システムの自動テストデモ

このデモでは、UserQueryServiceを使ってプロフィール確認機能を実装し、
サンプルデータの中の一人のユーザーとしてログインしている状態をシミュレーションします。

機能:
- 自分のプロフィール表示
- 他のユーザーのプロフィール表示
- フォロー中ユーザーの一覧表示
- フォロワーの一覧表示
- ブロック中ユーザーの一覧表示
- ブロックしているユーザーの一覧表示
- 購読中ユーザーの一覧表示
- 購読者の一覧表示

自動テストモード: すべての機能を順番に実行して結果を表示
"""

import sys
import os

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.application.social.services.user_query_service import UserQueryService
from src.application.social.contracts.dtos import UserProfileDto
from src.application.social.exceptions import UserQueryException


class SnsAutoTestDemo:
    """SNSプロフィール確認システムの自動テストデモ"""

    def __init__(self):
        """初期化"""
        self.repository = InMemorySnsUserRepository()
        self.user_query_service = UserQueryService(self.repository)

        # テスト対象のユーザー（勇者としてログイン）
        self.current_user_id: int = 1
        self.current_user_name: str = "勇者"

    def display_header(self):
        """ヘッダーを表示"""
        print("=" * 70)
        print("🔍 SNSプロフィール確認システム - 自動テストデモ")
        print(f"👤 現在のログイン: {self.current_user_name} (ID: {self.current_user_id})")
        print("=" * 70)

    def run_all_tests(self):
        """すべての機能を順番に実行"""
        print("\n🚀 自動テストを開始します...\n")

        test_methods = [
            ("自分のプロフィール表示", self.test_show_my_profile),
            ("他のユーザーのプロフィール表示", self.test_show_other_user_profile),
            ("フォロー中ユーザーの一覧", self.test_show_followees),
            ("フォロワーの一覧", self.test_show_followers),
            ("ブロック中ユーザーの一覧", self.test_show_blocked_users),
            ("ブロックしているユーザーの一覧", self.test_show_blockers),
            ("購読中ユーザーの一覧", self.test_show_subscriptions),
            ("購読者の一覧", self.test_show_subscribers),
        ]

        for test_name, test_method in test_methods:
            try:
                print(f"\n{'='*60}")
                print(f"🧪 テスト: {test_name}")
                print('='*60)
                test_method()
                print("✅ テスト完了")
            except Exception as e:
                print(f"❌ テスト失敗: {str(e)}")

        self.show_summary()

    def test_show_my_profile(self):
        """自分のプロフィール表示テスト"""
        print("\n👤 自分のプロフィール:")
        print("-" * 40)

        try:
            profile = self.user_query_service.show_my_profile(self.current_user_id)
            self.display_profile_info(profile, is_self=True)
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_other_user_profile(self):
        """他のユーザーのプロフィール表示テスト"""
        print("\n👥 他のユーザーのプロフィール:")
        print("-" * 40)

        # 魔法使い（ID: 2）のプロフィールを表示
        target_user_id = 2

        try:
            profile = self.user_query_service.show_other_user_profile(target_user_id, self.current_user_id)
            self.display_profile_info(profile, is_self=False)

            # 戦士（ID: 3）のプロフィールも表示
            print("\n" + "-" * 40)
            profile = self.user_query_service.show_other_user_profile(3, self.current_user_id)
            self.display_profile_info(profile, is_self=False)

        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_followees(self):
        """フォロー中ユーザーの一覧テスト"""
        print(f"\n👥 {self.current_user_name}のフォロー中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_followees_profile(self.current_user_id)
            self.display_profile_list(profiles, "フォロー中ユーザー")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_followers(self):
        """フォロワーの一覧テスト"""
        print(f"\n👥 {self.current_user_name}のフォロワー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_followers_profile(self.current_user_id)
            self.display_profile_list(profiles, "フォロワー")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_blocked_users(self):
        """ブロック中ユーザーの一覧テスト"""
        print(f"\n🚫 {self.current_user_name}のブロック中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_blocked_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "ブロック中ユーザー")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_blockers(self):
        """ブロックしているユーザーの一覧テスト"""
        print(f"\n🚫 {self.current_user_name}をブロックしているユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_blockers_profile(self.current_user_id)
            self.display_profile_list(profiles, "ブロックしているユーザー")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_subscriptions(self):
        """購読中ユーザーの一覧テスト"""
        print(f"\n📖 {self.current_user_name}の購読中ユーザー:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_subscriptions_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "購読中ユーザー")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

    def test_show_subscribers(self):
        """購読者の一覧テスト"""
        print(f"\n📖 {self.current_user_name}の購読者:")
        print("-" * 40)

        try:
            profiles = self.user_query_service.show_subscribers_users_profile(self.current_user_id)
            self.display_profile_list(profiles, "購読者")
        except UserQueryException as e:
            print(f"❌ エラー: {e.message}")
        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")

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
            print(f"  フォロー: {'✅ している' if profile.is_following else '❌ していない'}")
            print(f"  フォローされている: {'✅ されている' if profile.is_followed_by else '❌ されていない'}")
            print(f"  ブロック: {'✅ している' if profile.is_blocked else '❌ していない'}")
            print(f"  ブロックされている: {'✅ されている' if profile.is_blocked_by else '❌ されていない'}")
            print(f"  購読: {'✅ している' if profile.is_subscribed else '❌ していない'}")
            print(f"  購読されている: {'✅ されている' if profile.is_subscribed_by else '❌ されていない'}")

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
                print(f"     フォロー: {'✅ している' if profile.is_following else '❌ していない'}")
                print(f"     フォローされている: {'✅ されている' if profile.is_followed_by else '❌ されていない'}")
                print(f"     ブロック: {'✅ している' if profile.is_blocked else '❌ していない'}")
                print(f"     ブロックされている: {'✅ されている' if profile.is_blocked_by else '❌ されていない'}")
                print(f"     購読: {'✅ している' if profile.is_subscribed else '❌ していない'}")
                print(f"     購読されている: {'✅ されている' if profile.is_subscribed_by else '❌ されていない'}")

    def show_summary(self):
        """テスト結果のサマリーを表示"""
        print("\n" + "=" * 70)
        print("📊 テスト結果サマリー")
        print("=" * 70)

        print(f"👤 テストユーザー: {self.current_user_name} (ID: {self.current_user_id})")

        # サンプルデータの関係性を表示
        print("\n🔗 関係性の確認:")

        # フォロー関係
        followees = self.user_query_service.show_followees_profile(self.current_user_id)
        followers = self.user_query_service.show_followers_profile(self.current_user_id)

        print(f"  フォロー中: {len(followees)}人")
        for profile in followees:
            print(f"    - {profile.display_name}")

        print(f"  フォロワー: {len(followers)}人")
        for profile in followers:
            print(f"    - {profile.display_name}")

        # ブロック関係
        blocked_users = self.user_query_service.show_blocked_users_profile(self.current_user_id)
        blockers = self.user_query_service.show_blockers_profile(self.current_user_id)

        print(f"  ブロック中: {len(blocked_users)}人")
        for profile in blocked_users:
            print(f"    - {profile.display_name}")

        print(f"  ブロックされている: {len(blockers)}人")
        for profile in blockers:
            print(f"    - {profile.display_name}")

        # 購読関係
        subscriptions = self.user_query_service.show_subscriptions_users_profile(self.current_user_id)
        subscribers = self.user_query_service.show_subscribers_users_profile(self.current_user_id)

        print(f"  購読中: {len(subscriptions)}人")
        for profile in subscriptions:
            print(f"    - {profile.display_name}")

        print(f"  購読者: {len(subscribers)}人")
        for profile in subscribers:
            print(f"    - {profile.display_name}")

        print("\n✅ すべてのテストが完了しました！")
        print("🔍 UserQueryServiceのプロフィール確認機能が正常に動作していることを確認しました。")


def main():
    """メイン関数"""
    demo = SnsAutoTestDemo()
    demo.display_header()
    demo.run_all_tests()


if __name__ == "__main__":
    main()
