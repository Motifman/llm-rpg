#!/usr/bin/env python3
"""
掲示板と石碑システムのデモンストレーション

このデモでは以下の機能をテストします：
- 掲示板への投稿書き込み
- 掲示板からの投稿読み取り
- 石碑からの歴史情報読み取り
- 最大投稿数制限の動作
"""

from game.object.interactable import BulletinBoard, Monument
from game.action.actions.interactable_action import (
    WriteBulletinBoardCommand, ReadBulletinBoardCommand, ReadMonumentCommand
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.world.spot import Spot


def create_test_environment():
    """テスト環境を作成"""
    # ゲームコンテキストの設定
    from game.player.player_manager import PlayerManager
    spot_manager = SpotManager()
    player_manager = PlayerManager()
    game_context = GameContext(player_manager, spot_manager)
    
    # プレイヤーの作成
    from game.enums import Role
    player = Player("demo_player", "デモプレイヤー", Role.ADVENTURER)
    
    # スポットの作成
    village_square = Spot("village_square", "村の広場", "村の中心にある広場")
    ancient_ruins = Spot("ancient_ruins", "古代遺跡", "古代の王国の遺跡")
    
    # 掲示板の作成
    bulletin_board = BulletinBoard("village_bulletin", "村の掲示板")
    village_square.add_interactable(bulletin_board)
    
    # 石碑の作成
    historical_text = """
この地には古代の王国が栄えていた。
伝説によると、この王国は魔法の力で繁栄し、
多くの宝物を蓄えていたという。
しかし、ある日突然の災害により、
王国は一夜にして消滅した。
今もなお、その宝物はどこかに眠っていると伝えられている。
    """.strip()
    
    monument = Monument("ancient_monument", "古代の石碑", historical_text)
    ancient_ruins.add_interactable(monument)
    
    # スポットをマネージャーに追加
    spot_manager.add_spot(village_square)
    spot_manager.add_spot(ancient_ruins)
    
    return game_context, player, bulletin_board, monument


def demo_bulletin_board_features():
    """掲示板機能のデモンストレーション"""
    print("=== 掲示板機能デモ ===")
    
    game_context, player, board, monument = create_test_environment()
    player.set_current_spot_id("village_square")
    
    print(f"プレイヤー: {player.name}")
    print(f"現在地: {game_context.get_spot_manager().get_spot('village_square').name}")
    print(f"掲示板: {board.get_description()}")
    print()
    
    # 1. 空の掲示板を読む
    print("1. 空の掲示板を読む")
    command = ReadBulletinBoardCommand("掲示板")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 2. 掲示板に投稿を書き込む
    print("2. 掲示板に投稿を書き込む")
    posts = [
        "冒険者募集！一緒にダンジョンを探索しませんか？",
        "新しい武器屋がオープンしました。村の東側です。",
        "昨夜、森で不思議な光を見ました。誰か知りませんか？",
        "村の祭りが来週開催されます。皆さん参加してください！",
        "古い城の地下に宝物があるという噂を聞きました。"
    ]
    
    for i, post in enumerate(posts, 1):
        print(f"投稿{i}: {post}")
        command = WriteBulletinBoardCommand("掲示板", post)
        result = command.execute(player, game_context)
        print(result.to_feedback_message(player.name))
        print(f"現在の投稿数: {board.get_post_count()}")
        print()
    
    # 3. 投稿後の掲示板を読む
    print("3. 投稿後の掲示板を読む")
    command = ReadBulletinBoardCommand("掲示板")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 4. 空の投稿を試す
    print("4. 空の投稿を試す")
    command = WriteBulletinBoardCommand("掲示板", "")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()


def demo_monument_features():
    """石碑機能のデモンストレーション"""
    print("=== 石碑機能デモ ===")
    
    game_context, player, board, monument = create_test_environment()
    player.set_current_spot_id("ancient_ruins")
    
    print(f"プレイヤー: {player.name}")
    print(f"現在地: {game_context.get_spot_manager().get_spot('ancient_ruins').name}")
    print(f"石碑: {monument.get_description()}")
    print()
    
    # 石碑を読む
    print("石碑を読む")
    command = ReadMonumentCommand("石碑")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()


def demo_error_cases():
    """エラーケースのデモンストレーション"""
    print("=== エラーケースデモ ===")
    
    game_context, player, board, monument = create_test_environment()
    
    # 掲示板がない場所で掲示板アクションを試す
    print("1. 掲示板がない場所で掲示板アクションを試す")
    player.set_current_spot_id("ancient_ruins")  # 石碑しかない場所
    
    command = WriteBulletinBoardCommand("掲示板", "テスト投稿")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 石碑がない場所で石碑アクションを試す
    print("2. 石碑がない場所で石碑アクションを試す")
    player.set_current_spot_id("village_square")  # 掲示板しかない場所
    
    command = ReadMonumentCommand("石碑")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()


def demo_bulletin_board_limit():
    """掲示板の制限機能デモンストレーション"""
    print("=== 掲示板制限機能デモ ===")
    
    game_context, player, board, monument = create_test_environment()
    player.set_current_spot_id("village_square")
    
    print("掲示板に5つの投稿を書き込む（最大4つまで）")
    posts = [
        "1番目の投稿",
        "2番目の投稿", 
        "3番目の投稿",
        "4番目の投稿",
        "5番目の投稿（古い投稿が削除される）"
    ]
    
    for i, post in enumerate(posts, 1):
        print(f"\n{i}番目の投稿を書き込み:")
        command = WriteBulletinBoardCommand("掲示板", post)
        result = command.execute(player, game_context)
        print(result.to_feedback_message(player.name))
        print(f"現在の投稿数: {board.get_post_count()}")
    
    print("\n最終的な掲示板の内容:")
    command = ReadBulletinBoardCommand("掲示板")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()


def main():
    """メイン関数"""
    print("掲示板と石碑システムのデモンストレーション")
    print("=" * 50)
    print()
    
    # 掲示板機能のデモ
    demo_bulletin_board_features()
    print()
    
    # 石碑機能のデモ
    demo_monument_features()
    print()
    
    # エラーケースのデモ
    demo_error_cases()
    print()
    
    # 掲示板制限機能のデモ
    demo_bulletin_board_limit()
    print()
    
    print("デモンストレーション完了！")


if __name__ == "__main__":
    main() 