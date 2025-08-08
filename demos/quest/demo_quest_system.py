#!/usr/bin/env python3
"""
Questシステムのデモ
QuestSystemの主要機能を実演します
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.quest.quest_manager import QuestSystem
from game.quest.guild import AdventurerGuild, GuildMember
from game.quest.quest_data import Quest, QuestCondition
from game.quest.quest_helper import create_monster_hunt_quest, create_item_collection_quest, create_exploration_quest
from game.player.player import Player
from game.enums import QuestType, QuestStatus, QuestDifficulty, GuildRank, Role


def print_separator(title):
    """セパレーターを表示"""
    print("\n" + "="*60)
    print(f" {title} ")
    print("="*60)


def print_subsection(title):
    """サブセクションを表示"""
    print(f"\n--- {title} ---")


def demo_quest_condition():
    """QuestConditionのデモ"""
    print_separator("QuestCondition デモ")
    
    # クエスト条件の作成
    condition = QuestCondition(
        condition_type="kill_monster",
        target="goblin",
        required_count=3,
        description="ゴブリンを3体討伐"
    )
    
    print(f"条件: {condition.description}")
    print(f"初期進捗: {condition.get_progress_text()}")
    print(f"完了状態: {condition.is_completed()}")
    
    # 進捗更新
    print("\n進捗更新...")
    condition.update_progress(2)
    print(f"進捗: {condition.get_progress_text()}")
    print(f"完了状態: {condition.is_completed()}")
    
    condition.update_progress(1)
    print(f"進捗: {condition.get_progress_text()}")
    print(f"完了状態: {condition.is_completed()}")


def demo_quest_creation():
    """Quest作成のデモ"""
    print_separator("Quest作成 デモ")
    
    # 基本的なクエスト作成
    quest = Quest(
        quest_id="demo_quest_001",
        name="ゴブリン討伐",
        description="村を荒らすゴブリンを討伐してください",
        quest_type=QuestType.MONSTER_HUNT,
        difficulty=QuestDifficulty.D,
        client_id="client_001",
        guild_id="guild_001",
        reward_money=100
    )
    
    print(f"クエスト名: {quest.name}")
    print(f"説明: {quest.description}")
    print(f"タイプ: {quest.quest_type.value}")
    print(f"危険度: {quest.difficulty.value}")
    print(f"報酬: {quest.reward_money} ゴールド")
    print(f"手数料差引後: {quest.get_net_reward_money()} ゴールド")
    print(f"ギルド手数料: {quest.get_guild_fee()} ゴールド")
    print(f"状態: {quest.get_status_text()}")
    
    # 条件を追加
    condition = QuestCondition(
        condition_type="kill_monster",
        target="goblin",
        required_count=3,
        description="ゴブリンを3体討伐"
    )
    quest.conditions.append(condition)
    
    print(f"\n条件: {quest.get_progress_summary()}")


def demo_quest_lifecycle():
    """Questライフサイクルのデモ"""
    print_separator("Questライフサイクル デモ")
    
    # クエスト作成
    quest = create_monster_hunt_quest(
        "demo_quest_002", "スライム討伐", "スライムを5体討伐してください",
        "slime", 5, QuestDifficulty.E, "client_001", "guild_001", 200
    )
    
    print(f"クエスト: {quest.name}")
    print(f"初期状態: {quest.get_status_text()}")
    
    # 受注
    print("\nクエストを受注...")
    quest.accept_by("adventurer_001")
    print(f"受注後状態: {quest.get_status_text()}")
    print(f"受注者: {quest.accepted_by}")
    
    # 進行開始
    print("\nクエストを開始...")
    quest.start_progress()
    print(f"進行中状態: {quest.get_status_text()}")
    
    # 進捗更新
    print("\n進捗を更新...")
    quest.update_condition_progress("kill_monster", "slime", 3)
    print(f"進捗: {quest.get_progress_summary()}")
    print(f"完了状態: {quest.check_completion()}")
    
    quest.update_condition_progress("kill_monster", "slime", 2)
    print(f"進捗: {quest.get_progress_summary()}")
    print(f"完了状態: {quest.check_completion()}")
    
    # 完了
    print("\nクエストを完了...")
    quest.complete_quest()
    print(f"完了後状態: {quest.get_status_text()}")


def demo_guild_member():
    """GuildMemberのデモ"""
    print_separator("GuildMember デモ")
    
    # メンバー作成
    member = GuildMember(
        player_id="player_001",
        name="テスト冒険者"
    )
    
    print(f"プレイヤー: {member.name}")
    print(f"初期ランク: {member.get_rank_name()}")
    print(f"初期評判: {member.reputation}")
    print(f"完了クエスト数: {member.quests_completed}")
    print(f"総収入: {member.total_earnings}")
    
    # クエスト完了
    quest = Quest(
        quest_id="demo_quest_003",
        name="テストクエスト",
        description="テスト用",
        quest_type=QuestType.MONSTER_HUNT,
        difficulty=QuestDifficulty.C,
        client_id="client_001",
        guild_id="guild_001",
        reward_money=300
    )
    
    print(f"\nクエスト完了: {quest.name}")
    member.complete_quest(quest)
    
    print(f"更新後ランク: {member.get_rank_name()}")
    print(f"更新後評判: {member.reputation}")
    print(f"更新後完了数: {member.quests_completed}")
    print(f"更新後総収入: {member.total_earnings}")


def demo_adventurer_guild():
    """AdventurerGuildのデモ"""
    print_separator("AdventurerGuild デモ")
    
    # ギルド作成
    guild = AdventurerGuild("demo_guild", "デモギルド", "guild_hall")
    print(f"ギルド名: {guild.name}")
    print(f"場所: {guild.location_spot_id}")
    
    # プレイヤー作成・登録
    player = Player("player_001", "テスト冒険者", Role.ADVENTURER)
    print(f"\nプレイヤー登録: {player.get_name()}")
    guild.register_member(player)
    
    print(f"メンバー数: {len(guild.members)}")
    print(f"メンバーかどうか: {guild.is_member('player_001')}")
    
    # クエスト投稿
    quest = create_monster_hunt_quest(
        "demo_quest_004", "ゴブリン討伐", "ゴブリンを3体討伐してください",
        "goblin", 3, QuestDifficulty.D, "client_001", "demo_guild", 300
    )
    
    print(f"\nクエスト投稿: {quest.name}")
    guild.post_quest(quest, 300)
    
    print(f"利用可能クエスト数: {len(guild.available_quests)}")
    print(f"アクティブクエスト数: {len(guild.active_quests)}")
    
    # クエスト受注
    print(f"\nクエスト受注: {quest.name}")
    guild.accept_quest(quest.quest_id, "player_001")
    
    print(f"利用可能クエスト数: {len(guild.available_quests)}")
    print(f"アクティブクエスト数: {len(guild.active_quests)}")
    
    # 進捗更新
    print(f"\n進捗更新...")
    guild.update_quest_progress("player_001", "kill_monster", "goblin", 3)
    
    # クエスト完了
    print(f"クエスト完了...")
    result = guild.complete_quest(quest.quest_id, "player_001")
    print(f"完了結果: {result['success']}")
    print(f"報酬: {result['reward_money']} ゴールド")
    print(f"ギルド手数料: {result['guild_fee']} ゴールド")
    
    # 統計情報
    stats = guild.get_guild_stats()
    print(f"\nギルド統計:")
    print(f"  メンバー数: {stats['total_members']}")
    print(f"  利用可能クエスト: {stats['available_quests']}")
    print(f"  アクティブクエスト: {stats['active_quests']}")
    print(f"  完了クエスト: {stats['completed_quests']}")
    print(f"  ギルド資金: {stats['total_funds']}")


def demo_quest_system():
    """QuestSystemのデモ"""
    print_separator("QuestSystem デモ")
    
    # QuestSystem作成
    quest_system = QuestSystem()
    print("QuestSystemを作成しました")
    
    # プレイヤー作成
    adventurer = Player("adv_001", "冒険者", Role.ADVENTURER)
    client = Player("client_001", "依頼者", Role.CITIZEN)
    client.add_money(2000)  # 依頼用資金
    
    print(f"冒険者: {adventurer.get_name()}")
    print(f"依頼者: {client.get_name()} (資金: {client.get_money()} ゴールド)")
    
    # ギルド作成
    print_subsection("ギルド作成")
    guild = quest_system.create_guild("main_guild", "メインギルド", "guild_hall")
    print(f"ギルド作成: {guild.name}")
    
    # 冒険者登録
    print_subsection("冒険者登録")
    quest_system.register_player_to_guild(adventurer, "main_guild")
    print(f"冒険者をギルドに登録: {adventurer.get_name()}")
    
    # クエスト作成・投稿
    print_subsection("クエスト作成・投稿")
    quest = quest_system.create_monster_hunt_quest_for_guild(
        "main_guild", "ドラゴン討伐", "古代ドラゴンを1体討伐してください",
        "dragon", 1, QuestDifficulty.S, "client_001", 1000
    )
    print(f"クエスト作成: {quest.name}")
    print(f"危険度: {quest.difficulty.value}")
    print(f"報酬: {quest.reward_money} ゴールド")
    
    success = quest_system.post_quest_to_guild("main_guild", quest, client)
    print(f"クエスト投稿: {'成功' if success else '失敗'}")
    print(f"依頼者残金: {client.get_money()} ゴールド")
    
    # 利用可能クエスト確認
    print_subsection("利用可能クエスト確認")
    available_quests = quest_system.get_available_quests("adv_001")
    print(f"利用可能クエスト数: {len(available_quests)}")
    for q in available_quests:
        print(f"  - {q.name} ({q.difficulty.value}) - {q.reward_money} ゴールド")
    
    # クエスト受注
    print_subsection("クエスト受注")
    success = quest_system.accept_quest("adv_001", quest.quest_id)
    print(f"クエスト受注: {'成功' if success else '失敗'}")
    
    # アクティブクエスト確認
    active_quest = quest_system.get_active_quest("adv_001")
    if active_quest:
        print(f"アクティブクエスト: {active_quest.name}")
        print(f"進捗: {active_quest.get_progress_summary()}")
    
    # 進捗更新
    print_subsection("進捗更新")
    updated_quest = quest_system.handle_monster_kill("adv_001", "dragon", 1)
    if updated_quest:
        print(f"進捗更新: {updated_quest.get_progress_summary()}")
        print(f"状態: {updated_quest.get_status_text()}")
    
    # 完了チェック・報酬配布
    print_subsection("クエスト完了")
    completion_result = quest_system.check_quest_completion("adv_001")
    if completion_result:
        print(f"クエスト完了: {'成功' if completion_result['success'] else '失敗'}")
        print(f"報酬: {completion_result['reward_money']} ゴールド")
        print(f"ギルド手数料: {completion_result['guild_fee']} ゴールド")
        print(f"経験値: {completion_result['experience_gained']}")
        print(f"評判上昇: {completion_result['reputation_gained']}")
    
    # 完了後確認
    active_quest_after = quest_system.get_active_quest("adv_001")
    print(f"完了後アクティブクエスト: {'あり' if active_quest_after else 'なし'}")


def demo_multiple_quest_types():
    """複数クエストタイプのデモ"""
    print_separator("複数クエストタイプ デモ")
    
    quest_system = QuestSystem()
    adventurer = Player("adv_001", "冒険者", Role.ADVENTURER)
    client = Player("client_001", "依頼者", Role.CITIZEN)
    client.add_money(3000)
    
    # ギルド作成・プレイヤー登録
    guild = quest_system.create_guild("demo_guild", "デモギルド", "guild_hall")
    quest_system.register_player_to_guild(adventurer, "demo_guild")
    
    # モンスター討伐クエスト
    print_subsection("モンスター討伐クエスト")
    monster_quest = quest_system.create_monster_hunt_quest_for_guild(
        "demo_guild", "スライム討伐", "スライムを10体討伐してください",
        "slime", 10, QuestDifficulty.E, "client_001", 200
    )
    quest_system.post_quest_to_guild("demo_guild", monster_quest, client)
    print(f"作成: {monster_quest.name} - {monster_quest.reward_money} ゴールド")
    
    # アイテム収集クエスト
    print_subsection("アイテム収集クエスト")
    item_quest = quest_system.create_item_collection_quest_for_guild(
        "demo_guild", "鉱石収集", "鉄鉱石を5個収集してください",
        "iron_ore", 5, QuestDifficulty.D, "client_001", 300
    )
    quest_system.post_quest_to_guild("demo_guild", item_quest, client)
    print(f"作成: {item_quest.name} - {item_quest.reward_money} ゴールド")
    
    # 探索クエスト
    print_subsection("探索クエスト")
    exploration_quest = quest_system.create_exploration_quest_for_guild(
        "demo_guild", "迷宮探索", "地下迷宮を探索してください",
        "underground_labyrinth", QuestDifficulty.C, "client_001", 500
    )
    quest_system.post_quest_to_guild("demo_guild", exploration_quest, client)
    print(f"作成: {exploration_quest.name} - {exploration_quest.reward_money} ゴールド")
    
    # 利用可能クエスト一覧
    print_subsection("利用可能クエスト一覧")
    available_quests = quest_system.get_available_quests("adv_001")
    print(f"利用可能クエスト数: {len(available_quests)}")
    
    for i, quest in enumerate(available_quests, 1):
        print(f"{i}. {quest.name}")
        print(f"   タイプ: {quest.quest_type.value}")
        print(f"   危険度: {quest.difficulty.value}")
        print(f"   報酬: {quest.reward_money} ゴールド")
        print(f"   進捗: {quest.get_progress_summary()}")
        print()


def demo_quest_statistics():
    """クエスト統計のデモ"""
    print_separator("クエスト統計 デモ")
    
    quest_system = QuestSystem()
    
    # 複数ギルド作成
    guild1 = quest_system.create_guild("guild_1", "ギルド1", "hall_1")
    guild2 = quest_system.create_guild("guild_2", "ギルド2", "hall_2")
    guild3 = quest_system.create_guild("guild_3", "ギルド3", "hall_3")
    
    # プレイヤー作成・登録
    players = []
    for i in range(5):
        player = Player(f"player_{i+1:03d}", f"プレイヤー{i+1}", Role.ADVENTURER)
        players.append(player)
        quest_system.register_player_to_guild(player, f"guild_{(i % 3) + 1}")
    
    # クエスト投稿
    client = Player("client_001", "依頼者", Role.CITIZEN)
    client.add_money(5000)
    
    quests = [
        ("スライム討伐", "slime", 5, QuestDifficulty.E, 100),
        ("ゴブリン討伐", "goblin", 3, QuestDifficulty.D, 200),
        ("オーク討伐", "orc", 2, QuestDifficulty.C, 300),
        ("薬草収集", "herb", 10, QuestDifficulty.E, 150),
        ("鉱石収集", "iron_ore", 5, QuestDifficulty.D, 250),
        ("遺跡探索", "ancient_ruins", 1, QuestDifficulty.C, 400),
    ]
    
    for i, (name, target, count, difficulty, reward) in enumerate(quests):
        quest = quest_system.create_monster_hunt_quest_for_guild(
            f"guild_{(i % 3) + 1}", name, f"{name}を{count}回実行してください",
            target, count, difficulty, "client_001", reward
        )
        quest_system.post_quest_to_guild(f"guild_{(i % 3) + 1}", quest, client)
    
    # 統計情報取得
    stats = quest_system.get_guild_statistics()
    
    print("全体統計:")
    print(f"  総ギルド数: {stats['total_guilds']}")
    print(f"  総メンバー数: {stats['total_members']}")
    print(f"  総利用可能クエスト数: {stats['total_available_quests']}")
    print(f"  総アクティブクエスト数: {stats['total_active_quests']}")
    print(f"  総完了クエスト数: {stats['total_completed_quests']}")
    
    print("\nギルド別詳細:")
    for guild_detail in stats['guild_details']:
        print(f"  {guild_detail['name']}:")
        print(f"    メンバー数: {guild_detail['total_members']}")
        print(f"    利用可能クエスト: {guild_detail['available_quests']}")
        print(f"    アクティブクエスト: {guild_detail['active_quests']}")
        print(f"    完了クエスト: {guild_detail['completed_quests']}")
        print(f"    ギルド資金: {guild_detail['total_funds']}")


def demo_player_quest_history():
    """プレイヤークエスト履歴のデモ"""
    print_separator("プレイヤークエスト履歴 デモ")
    
    quest_system = QuestSystem()
    adventurer = Player("adv_001", "冒険者", Role.ADVENTURER)
    client = Player("client_001", "依頼者", Role.CITIZEN)
    client.add_money(1000)
    
    # ギルド作成・プレイヤー登録
    guild = quest_system.create_guild("demo_guild", "デモギルド", "guild_hall")
    quest_system.register_player_to_guild(adventurer, "demo_guild")
    
    # クエスト作成・投稿・受注
    quest = quest_system.create_monster_hunt_quest_for_guild(
        "demo_guild", "テストクエスト", "テスト用クエスト",
        "goblin", 1, QuestDifficulty.E, "client_001", 100
    )
    quest_system.post_quest_to_guild("demo_guild", quest, client)
    quest_system.accept_quest("adv_001", quest.quest_id)
    
    # 履歴取得
    history = quest_system.get_player_quest_history("adv_001")
    
    print("プレイヤー履歴:")
    print(f"  プレイヤーID: {history['player_id']}")
    print(f"  ギルド情報:")
    print(f"    ギルドID: {history['guild_info']['guild_id']}")
    print(f"    ギルド名: {history['guild_info']['guild_name']}")
    
    if history['member_info']:
        member = history['member_info']
        print(f"  メンバー情報:")
        print(f"    名前: {member['name']}")
        print(f"    ランク: {member['rank']}")
        print(f"    評判: {member['reputation']}")
        print(f"    完了クエスト数: {member['quests_completed']}")
        print(f"    総収入: {member['total_earnings']}")
    
    if history['active_quest']:
        active = history['active_quest']
        print(f"  アクティブクエスト:")
        print(f"    名前: {active['name']}")
        print(f"    状態: {active['status']}")
        print(f"    進捗: {active['progress']}")
        print(f"    報酬: {active['reward_money']} ゴールド")
    else:
        print(f"  アクティブクエスト: なし")
    
    print(f"  利用可能クエスト数: {history['available_quests_count']}")


def main():
    """メイン関数"""
    print("Questシステム デモ")
    print("=" * 60)
    
    try:
        # 各デモを実行
        demo_quest_condition()
        demo_quest_creation()
        demo_quest_lifecycle()
        demo_guild_member()
        demo_adventurer_guild()
        demo_quest_system()
        demo_multiple_quest_types()
        demo_quest_statistics()
        demo_player_quest_history()
        
        print_separator("デモ完了")
        print("Questシステムのデモが完了しました。")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 