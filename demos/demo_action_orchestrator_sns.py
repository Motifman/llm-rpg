#!/usr/bin/env python3
"""
ActionOrchestratorを使用したSNSアクションのデモ

このデモでは、ActionOrchestratorを使用してSNS関連のアクションの
行動候補の提示、選択、実行、結果取得を実際に体験できます。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.core.game_context import GameContextBuilder
from game.player.player_manager import PlayerManager
from game.player.player import Player
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.sns.sns_manager import SnsManager
from game.action.action_orchestrator import ActionOrchestrator
from game.enums import Role, PostVisibility


def print_separator(title):
    """セパレーターを表示"""
    print("\n" + "="*60)
    print(f" {title} ")
    print("="*60)


def print_subsection(title):
    """サブセクションを表示"""
    print(f"\n--- {title} ---")


def setup_game_context():
    """ゲームコンテキストをセットアップ"""
    # プレイヤーマネージャーを初期化
    player_manager = PlayerManager()
    
    # テストプレイヤーを作成
    test_player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
    test_player.set_current_spot_id("test_spot")
    player_manager.add_player(test_player)
    
    # スポットマネージャーを初期化
    spot_manager = SpotManager()
    
    # テストスポットを作成
    test_spot = Spot("test_spot", "テストスポット", "テスト用のスポットです")
    spot_manager.add_spot(test_spot)
    
    # SNSマネージャーを初期化
    sns_manager = SnsManager()
    
    # テスト用SNSユーザーを作成
    sns_manager.create_user("test_player", "テストプレイヤー", "テスト用のユーザーです")
    sns_manager.create_user("alice", "アリス", "よろしくお願いします！")
    sns_manager.create_user("bob", "ボブ", "エンジニアです")
    sns_manager.create_user("charlie", "チャーリー", "デザイナーです")
    
    # GameContextを作成
    game_context = GameContextBuilder()\
        .with_player_manager(player_manager)\
        .with_spot_manager(spot_manager)\
        .with_sns_manager(sns_manager)\
        .build()
    
    return game_context


def demo_action_candidates():
    """アクション候補の取得デモ"""
    print_separator("アクション候補の取得")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    # アクション候補を取得
    candidates = orchestrator.get_action_candidates_for_llm("test_player")
    
    print_subsection("利用可能なアクション一覧")
    print(f"総アクション数: {len(candidates)}")
    
    # SNS関連のアクションを抽出
    sns_actions = [c for c in candidates if c['action_name'].startswith('SNS')]
    other_actions = [c for c in candidates if not c['action_name'].startswith('SNS')]
    
    print(f"SNS関連アクション数: {len(sns_actions)}")
    print(f"その他のアクション数: {len(other_actions)}")
    
    print_subsection("SNS関連アクション詳細")
    for action in sns_actions:
        print(f"アクション名: {action['action_name']}")
        print(f"説明: {action['action_description']}")
        print(f"タイプ: {action['action_type']}")
        print(f"必要な引数数: {len(action['required_arguments'])}")
        for arg in action['required_arguments']:
            print(f"  - {arg['name']}: {arg['description']} ({arg['type']})")
        print()


def demo_sns_user_info_action():
    """SNSユーザー情報取得アクションのデモ"""
    print_separator("SNSユーザー情報取得アクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    print_subsection("アクション実行")
    action_args = {"user_id": "alice"}
    result = orchestrator.execute_llm_action("test_player", "SNSユーザー情報取得", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"ユーザー情報: {result.user_info.format_for_display()}")


def demo_sns_post_action():
    """SNS投稿アクションのデモ"""
    print_separator("SNS投稿アクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    print_subsection("投稿作成")
    action_args = {
        "content": "ActionOrchestratorを使用した投稿です！ #デモ #テスト",
        "hashtags": ["#デモ", "#テスト"],
        "visibility": "public",
        "allowed_users": []
    }
    result = orchestrator.execute_llm_action("test_player", "SNS投稿", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"投稿ID: {result.post_id}")
        
        # 投稿を確認
        sns_manager = game_context.get_sns_manager()
        post = sns_manager.get_post(result.post_id)
        if post:
            print(f"投稿内容: {post.content}")
            print(f"ハッシュタグ: {post.hashtags}")


def demo_sns_timeline_action():
    """SNSタイムライン取得アクションのデモ"""
    print_separator("SNSタイムライン取得アクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    # テスト用の投稿を作成
    sns_manager = game_context.get_sns_manager()
    sns_manager.create_post("alice", "アリスの投稿 #初投稿")
    sns_manager.create_post("bob", "ボブの投稿 #プログラミング")
    sns_manager.create_post("charlie", "チャーリーの投稿 #デザイン")
    
    print_subsection("グローバルタイムライン取得")
    action_args = {
        "timeline_type": "global",
        "hashtag": ""
    }
    result = orchestrator.execute_llm_action("test_player", "SNSタイムライン取得", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"取得された投稿数: {len(result.posts)}")
        print("投稿一覧:")
        for i, post in enumerate(result.posts, 1):
            print(f"  {i}. {post}")


def demo_sns_like_action():
    """SNSいいねアクションのデモ"""
    print_separator("SNSいいねアクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    # テスト用の投稿を作成
    sns_manager = game_context.get_sns_manager()
    post = sns_manager.create_post("alice", "いいねテスト投稿")
    
    print_subsection("いいね実行")
    action_args = {"post_id": post.post_id}
    result = orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"投稿ID: {result.post_id}")
        
        # いいね状況を確認
        likes_count = sns_manager.get_post_likes_count(post.post_id)
        has_liked = sns_manager.has_liked("test_player", post.post_id)
        print(f"投稿のいいね数: {likes_count}")
        print(f"テストプレイヤーがいいね済み: {has_liked}")


def demo_sns_reply_action():
    """SNS返信アクションのデモ"""
    print_separator("SNS返信アクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    # テスト用の投稿を作成
    sns_manager = game_context.get_sns_manager()
    post = sns_manager.create_post("alice", "返信テスト投稿")
    
    print_subsection("返信実行")
    action_args = {
        "post_id": post.post_id,
        "content": "ActionOrchestratorからの返信です！"
    }
    result = orchestrator.execute_llm_action("test_player", "SNS投稿に返信", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"投稿ID: {result.post_id}")
        print(f"返信ID: {result.reply_id}")
        
        # 返信状況を確認
        replies_count = sns_manager.get_post_replies_count(post.post_id)
        replies = sns_manager.get_post_replies(post.post_id)
        print(f"投稿の返信数: {replies_count}")
        print("返信一覧:")
        for i, reply in enumerate(replies, 1):
            print(f"  {i}. {reply.user_id}: {reply.content}")


def demo_sns_notification_action():
    """SNS通知アクションのデモ"""
    print_separator("SNS通知アクション")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    # 通知を生成するためのアクションを実行
    sns_manager = game_context.get_sns_manager()
    sns_manager.follow_user("alice", "test_player")
    post = sns_manager.create_post("alice", "通知テスト投稿")
    sns_manager.like_post("bob", post.post_id)
    sns_manager.reply_to_post("charlie", post.post_id, "通知テスト返信")
    
    print_subsection("通知取得")
    action_args = {"unread_only": "false"}
    result = orchestrator.execute_llm_action("test_player", "SNS通知取得", action_args)
    
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.success:
        print(f"取得された通知数: {len(result.notifications)}")
        print("通知一覧:")
        for i, notification in enumerate(result.notifications, 1):
            print(f"  {i}. {notification}")


def demo_integration_flow():
    """統合フローデモ"""
    print_separator("統合フローデモ")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    print_subsection("1. 投稿作成")
    post_action_args = {
        "content": "統合テスト投稿です！ #統合テスト #ActionOrchestrator",
        "hashtags": ["#統合テスト", "#ActionOrchestrator"],
        "visibility": "public",
        "allowed_users": []
    }
    post_result = orchestrator.execute_llm_action("test_player", "SNS投稿", post_action_args)
    print(f"投稿作成: {'成功' if post_result.success else '失敗'}")
    if post_result.success:
        print(f"投稿ID: {post_result.post_id}")
    
    print_subsection("2. タイムライン取得")
    timeline_action_args = {
        "timeline_type": "global",
        "hashtag": ""
    }
    timeline_result = orchestrator.execute_llm_action("test_player", "SNSタイムライン取得", timeline_action_args)
    print(f"タイムライン取得: {'成功' if timeline_result.success else '失敗'}")
    
    print_subsection("3. 投稿にいいね")
    like_action_args = {"post_id": post_result.post_id}
    like_result = orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", like_action_args)
    print(f"いいね: {'成功' if like_result.success else '失敗'}")
    
    print_subsection("4. 投稿に返信")
    reply_action_args = {
        "post_id": post_result.post_id,
        "content": "統合テスト返信です！"
    }
    reply_result = orchestrator.execute_llm_action("test_player", "SNS投稿に返信", reply_action_args)
    print(f"返信: {'成功' if reply_result.success else '失敗'}")
    
    print_subsection("5. 通知取得")
    notification_action_args = {"unread_only": "false"}
    notification_result = orchestrator.execute_llm_action("test_player", "SNS通知取得", notification_action_args)
    print(f"通知取得: {'成功' if notification_result.success else '失敗'}")
    
    print_subsection("最終結果確認")
    sns_manager = game_context.get_sns_manager()
    post = sns_manager.get_post(post_result.post_id)
    if post:
        print(f"投稿内容: {post.content}")
        print(f"いいね数: {sns_manager.get_post_likes_count(post_result.post_id)}")
        print(f"返信数: {sns_manager.get_post_replies_count(post_result.post_id)}")
        print(f"通知数: {len(sns_manager.get_user_notifications('test_player'))}")


def demo_error_handling():
    """エラーハンドリングデモ"""
    print_separator("エラーハンドリングデモ")
    
    game_context = setup_game_context()
    orchestrator = ActionOrchestrator(game_context)
    
    print_subsection("存在しない投稿IDでいいね")
    action_args = {"post_id": "invalid_post_id"}
    result = orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", action_args)
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"エラーメッセージ: {result.message}")
    
    print_subsection("空の返信内容で返信")
    post = game_context.get_sns_manager().create_post("alice", "エラーテスト投稿")
    action_args = {
        "post_id": post.post_id,
        "content": ""
    }
    result = orchestrator.execute_llm_action("test_player", "SNS投稿に返信", action_args)
    print(f"実行結果: {'成功' if result.success else '失敗'}")
    print(f"エラーメッセージ: {result.message}")


def main():
    """メイン関数"""
    print("ActionOrchestratorを使用したSNSアクション デモ")
    print("このデモでは、ActionOrchestratorを使用してSNS関連のアクションの")
    print("行動候補の提示、選択、実行、結果取得を実際に体験できます。")
    
    try:
        # 各デモを実行
        demo_action_candidates()
        demo_sns_user_info_action()
        demo_sns_post_action()
        demo_sns_timeline_action()
        demo_sns_like_action()
        demo_sns_reply_action()
        demo_sns_notification_action()
        demo_integration_flow()
        demo_error_handling()
        
        print_separator("デモ完了")
        print("ActionOrchestratorを使用したSNSアクションのデモが完了しました！")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 