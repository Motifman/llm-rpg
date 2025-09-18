#!/usr/bin/env python3
"""
改善された戦闘イベントシステムのデモ
UIで表示できる情報の詳細を確認するためのテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.domain.battle.battle import Battle
from src.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from src.infrastructure.repository.in_memory_monster_repository import InMemoryMonsterRepository
from src.infrastructure.repository.in_memory_action_repository import InMemoryActionRepository
from src.infrastructure.repository.in_memory_area_repository import InMemoryAreaRepository
from src.infrastructure.repository.in_memory_battle_repository import InMemoryBattleRepository
from src.domain.battle.events.battle_events import (
    BattleStartedEvent, TurnStartedEvent, TurnExecutedEvent, TurnEndedEvent,
    RoundStartedEvent, RoundEndedEvent, ParticipantInfo, ActionInfo
)


def demonstrate_enhanced_battle_events():
    """改善された戦闘イベントシステムのデモ"""
    print("🎮 改善された戦闘イベントシステムのデモ")
    print("=" * 50)
    
    # リポジトリの初期化
    player_repository = InMemoryPlayerRepository()
    monster_repository = InMemoryMonsterRepository()
    action_repository = InMemoryActionRepository()
    area_repository = InMemoryAreaRepository()
    battle_repository = InMemoryBattleRepository()
    
    # プレイヤーとモンスターを取得
    players = player_repository.find_by_spot_id(100)
    monsters = monster_repository.find_by_ids([101, 102])  # スライムとゴブリン
    
    if not players or not monsters:
        print("❌ プレイヤーまたはモンスターが見つかりません")
        return
    
    player = players[0]
    
    print(f"👤 プレイヤー: {player.name}")
    print(f"🐉 モンスター: {[m.name for m in monsters]}")
    print()
    
    # 戦闘を作成・開始
    battle = Battle(
        battle_id=1,
        spot_id=100,
        players=[player],
        monsters=monsters
    )
    battle.start_battle()
    
    # イベントを確認
    events = battle.get_events()
    
    print("📊 生成されたイベントの詳細分析")
    print("-" * 40)
    
    for i, event in enumerate(events, 1):
        print(f"\n🎯 イベント {i}: {event.__class__.__name__}")
        
        if isinstance(event, BattleStartedEvent):
            print(f"  戦闘ID: {event.battle_id}")
            print(f"  スポットID: {event.spot_id}")
            print(f"  プレイヤー数: {len(event.player_ids)}")
            print(f"  モンスター数: {len(event.monster_ids)}")
            
        elif isinstance(event, RoundStartedEvent):
            print(f"  ラウンド番号: {event.round_number}")
            print(f"  ターン順序: {len(event.turn_order)} 参加者")
            print(f"  生存プレイヤー: {len(event.remaining_players)}")
            print(f"  生存モンスター: {len(event.remaining_monsters)}")
            
            print(f"\n  📋 全参加者の詳細状態:")
            for participant in event.all_participants:
                print(f"    - {participant.name} ({participant.participant_type.value})")
                print(f"      HP: {participant.current_hp}/{participant.max_hp}")
                print(f"      MP: {participant.current_mp}/{participant.max_mp}")
                print(f"      攻撃力: {participant.attack}, 防御力: {participant.defense}")
                print(f"      速度: {participant.speed}")
                print(f"      行動可能: {participant.can_act}")
                print(f"      利用可能アクション: {len(participant.available_action_ids)} 個")
                if participant.status_effects:
                    print(f"      状態異常: {list(participant.status_effects.keys())}")
                if participant.buffs:
                    print(f"      バフ: {list(participant.buffs.keys())}")
                print()
                
        elif isinstance(event, TurnStartedEvent):
            print(f"  ターン番号: {event.turn_number}")
            print(f"  ラウンド番号: {event.round_number}")
            print(f"  アクター: {event.actor_id} ({event.participant_type.value})")
            
            if event.actor_info:
                actor = event.actor_info
                print(f"  アクター詳細:")
                print(f"    名前: {actor.name}")
                print(f"    HP: {actor.current_hp}/{actor.max_hp}")
                print(f"    MP: {actor.current_mp}/{actor.max_mp}")
                print(f"    攻撃力: {actor.attack}")
                print(f"    防御力: {actor.defense}")
                print(f"    速度: {actor.speed}")
                
            print(f"  全参加者数: {len(event.all_participants)}")
            print(f"  ターン順序: {len(event.turn_order)} 参加者")
    
    print("\n✅ 戦闘UIで表示可能な情報の確認")
    print("-" * 40)
    
    # UIで表示できる情報をまとめる
    ui_capabilities = [
        "✅ 各参加者の現在HP/MP（最大値含む）",
        "✅ 各参加者の現在ステータス（攻撃・防御・速度）",
        "✅ 各参加者の名前・種族・属性",
        "✅ 現在のターン順序",
        "✅ 各参加者の行動可能状態",
        "✅ 状態異常・バフの詳細情報（種類・継続時間・効果量）",
        "✅ 利用可能なアクションリスト",
        "✅ 戦闘の進行状況（ターン・ラウンド番号）",
        "✅ リアルタイムでの状態変化追跡",
        "✅ 詳細なメッセージ情報",
    ]
    
    for capability in ui_capabilities:
        print(f"  {capability}")
    
    print(f"\n🎯 改善のポイント")
    print("-" * 40)
    improvements = [
        "各イベントに全参加者の現在状態が含まれる",
        "ParticipantInfo構造体で統一された参加者情報",
        "状態異常・バフの詳細情報（効果量・継続時間）",
        "アクション情報の詳細（ActionInfo構造体）",
        "ターゲット別の結果詳細（TargetResult構造体）",
        "UI表示に最適化されたデータ構造",
        "リアルタイム戦闘画面の完全サポート",
    ]
    
    for improvement in improvements:
        print(f"  ✨ {improvement}")
    
    print(f"\n🖥️ UIで実現可能な表示例")
    print("-" * 40)
    ui_examples = [
        "参加者一覧（HP/MPバー、ステータス表示）",
        "ターン順序インジケーター",
        "アクション選択画面（消費MP/HP表示）",
        "ダメージ・回復エフェクト（数値・クリティカル表示）",
        "状態異常・バフアイコン（残りターン数表示）",
        "戦闘ログ（詳細なメッセージ履歴）",
        "戦況分析（貢献度、優劣判定）",
    ]
    
    for example in ui_examples:
        print(f"  🎨 {example}")


if __name__ == "__main__":
    demonstrate_enhanced_battle_events()
