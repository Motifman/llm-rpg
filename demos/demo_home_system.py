#!/usr/bin/env python3
"""
家のシステムデモ
権限ベースのアクションを持つHomeSpotの動作を演示します。
"""

from game.world.spots.home_spot import HomeSpot
from game.action.actions.home_action import SleepActionStrategy, WriteDiaryActionStrategy
from game.player.player import Player
from game.player.status import Status
from game.enums import Role, Permission
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.player.player_manager import PlayerManager


def create_demo_players():
    """デモ用のプレイヤーを作成"""
    # オーナープレイヤー
    owner = Player("owner_player", "オーナー", Role.ADVENTURER)
    owner.status = Status()
    owner.status.set_hp(60)  # 体力を減らしておく
    owner.status.set_mp(20)  # マナを減らしておく
    owner.status.set_experience_points(50)
    owner.set_current_spot_id("home_spot")
    
    # ゲストプレイヤー
    guest = Player("guest_player", "ゲスト", Role.ADVENTURER)
    guest.status = Status()
    guest.status.set_hp(70)
    guest.status.set_mp(30)
    guest.status.set_experience_points(20)
    guest.set_current_spot_id("home_spot")
    
    return owner, guest


def create_demo_game_context(home_spot):
    """デモ用のGameContextを作成"""
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    spot_manager.add_spot(home_spot)
    game_context = GameContext(player_manager, spot_manager)
    return game_context


def print_player_status(player, title=""):
    """プレイヤーの状態を表示"""
    print(f"\n{title}")
    print(f"名前: {player.name}")
    print(f"HP: {player.status.get_hp()}/{player.status.get_max_hp()}")
    print(f"MP: {player.status.get_mp()}/{player.status.get_max_mp()}")
    print(f"経験値: {player.status.get_experience_points()}")


def demo_sleep_action(player, home_spot, game_context):
    """睡眠アクションのデモ"""
    print(f"\n=== {player.name}の睡眠アクション ===")
    print_player_status(player, "睡眠前")
    
    sleep_strategy = SleepActionStrategy()
    
    # 権限チェック
    can_sleep = sleep_strategy.can_execute(player, game_context)
    print(f"睡眠可能: {can_sleep}")
    
    if can_sleep:
        # コマンド構築と実行
        command = sleep_strategy.build_action_command(player, game_context)
        result = command.execute(player, game_context)
        
        print(f"結果: {result.message}")
        print(f"回復量 - HP: {result.health_restored}, MP: {result.mana_restored}")
        print_player_status(player, "睡眠後")
    else:
        print("権限が不足しているため睡眠できません。")


def demo_write_diary_action(player, home_spot, game_context):
    """日記を書くアクションのデモ"""
    print(f"\n=== {player.name}の日記を書くアクション ===")
    print_player_status(player, "日記を書く前")
    
    diary_strategy = WriteDiaryActionStrategy()
    
    # 権限チェック
    can_write = diary_strategy.can_execute(player, game_context)
    print(f"日記を書く可能: {can_write}")
    
    if can_write:
        # コマンド構築と実行
        content = "今日は冒険に行きました。新しい友達もできて楽しかったです。"
        command = diary_strategy.build_action_command(
            player, 
            game_context, 
            content=content
        )
        result = command.execute(player, game_context)
        
        print(f"結果: {result.message}")
        print(f"日記の内容: {result.content}")
        print(f"獲得経験値: {result.exp_gained}")
        print_player_status(player, "日記を書いた後")
    else:
        print("権限が不足しているため日記を書けません。")


def demo_permission_system(home_spot):
    """権限システムのデモ"""
    print("\n=== 権限システムのデモ ===")
    
    # 様々な権限を持つプレイヤーを作成
    players = {
        "owner": ("オーナー", Permission.OWNER),
        "employee": ("従業員", Permission.EMPLOYEE),
        "customer": ("顧客", Permission.CUSTOMER),
        "guest": ("ゲスト", Permission.GUEST),
        "denied": ("拒否", Permission.DENIED)
    }
    
    for player_id, (name, permission) in players.items():
        player = Player(player_id, name, Role.ADVENTURER)
        player.set_current_spot_id("home_spot")
        
        # 権限を設定
        home_spot.set_player_permission(player_id, permission)
        
        # 利用可能なアクションを確認
        available_actions = home_spot.get_available_actions_for_player(player_id)
        action_names = [action.get_name() for action in available_actions.values()]
        
        print(f"{name} ({permission.value}): {action_names}")


def main():
    """メインデモ"""
    print("🏠 家のシステムデモ")
    print("=" * 50)
    
    # プレイヤーを作成
    owner, guest = create_demo_players()
    
    # HomeSpotを作成
    home_spot = HomeSpot("home_spot", "owner_player")
    
    # GameContextを作成
    game_context = create_demo_game_context(home_spot)
    
    # 権限システムのデモ
    demo_permission_system(home_spot)
    
    # オーナーのアクション実行
    demo_sleep_action(owner, home_spot, game_context)
    demo_write_diary_action(owner, home_spot, game_context)
    
    # ゲストのアクション実行（権限なし）
    demo_sleep_action(guest, home_spot, game_context)
    demo_write_diary_action(guest, home_spot, game_context)
    
    print("\n" + "=" * 50)
    print("デモ完了！")


if __name__ == "__main__":
    main() 