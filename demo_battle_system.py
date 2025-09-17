#!/usr/bin/env python3
"""
戦闘システムのデモンストレーション
BattleApplicationServiceの基本的な使用方法を示すサンプルコード
"""

import traceback
from src.application.battle.services.battle_service import BattleApplicationService
from src.application.battle.contracts.dtos import PlayerActionDto
from src.infrastructure.notifier.console_notifier import ConsoleNotifier
from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
from src.infrastructure.repository.player_repository_impl import PlayerRepositoryImpl
from src.infrastructure.repository.action_repository_impl import ActionRepositoryImpl
from src.infrastructure.repository.battle_repository_impl import BattleRepositoryImpl
from src.infrastructure.repository.area_repository_impl import AreaRepositoryImpl
from src.infrastructure.repository.monster_repository_impl import MonsterRepositoryImpl
from src.domain.battle.services.monster_action_service import MonsterActionService
from src.domain.battle.battle_service import BattleLogicService
from src.domain.battle.battle_enum import ParticipantType


def create_sample_battle_service() -> BattleApplicationService:
    """サンプルのBattleApplicationServiceを作成"""
    # 依存関係の作成
    notifier = ConsoleNotifier()
    event_publisher = InMemoryEventPublisher()
    player_repository = PlayerRepositoryImpl()
    action_repository = ActionRepositoryImpl()
    battle_repository = BattleRepositoryImpl()
    area_repository = AreaRepositoryImpl()
    monster_repository = MonsterRepositoryImpl()
    monster_action_service = MonsterActionService()
    battle_logic_service = BattleLogicService()

    # サービス作成
    battle_service = BattleApplicationService(
        battle_repository=battle_repository,
        player_repository=player_repository,
        area_repository=area_repository,
        monster_repository=monster_repository,
        action_repository=action_repository,
        battle_logic_service=battle_logic_service,
        monster_action_service=monster_action_service,
        notifier=notifier,
        event_publisher=event_publisher
    )

    return battle_service


def demo_battle_flow():
    """戦闘フローのデモンストレーション"""
    print("=== 戦闘システム実動作デモ ===\n")

    try:
        # サービス作成
        battle_service = create_sample_battle_service()
        print("✅ BattleApplicationService作成完了\n")

        # 1. 戦闘開始
        print("🚀 1. 戦闘開始")
        player_id = 1
        print(f"プレイヤー{player_id}が戦闘を開始...")
        
        battle_service.start_battle(player_id)
        print("✅ 戦闘開始成功\n")

        # 戦闘状態確認
        battle = battle_service.get_battle_in_spot(1)  # スポット1で戦闘確認
        if battle:
            print(f"📊 戦闘ID: {battle.battle_id}")
            print(f"📊 参加プレイヤー: {len(battle.get_player_ids())}人")
            print(f"📊 モンスター種類: {len(battle.get_monster_type_ids())}種類")
            print(f"📊 現在のターン: {battle._current_turn}")
            print(f"📊 現在のラウンド: {battle._current_round}")
            
            current_actor = battle.get_current_actor()
            if current_actor:
                actor_type = "プレイヤー" if current_actor.participant_type == ParticipantType.PLAYER else "モンスター"
                print(f"📊 現在のアクター: {actor_type} (ID: {current_actor.entity_id})")
            print()

        # 2. プレイヤー2を戦闘に参加させる
        print("👥 2. プレイヤー参加")
        player2_id = 2
        print(f"プレイヤー{player2_id}が戦闘に参加...")
        
        battle_service.join_battle(battle.battle_id, player2_id)
        print("✅ プレイヤー参加成功\n")

        # 3. 数ターン実行してみる
        print("⚔️ 3. 戦闘ターン実行")
        max_turns = 5  # 最大5ターン実行
        
        for turn in range(max_turns):
            print(f"\n--- ターン {turn + 1} ---")
            
            if not battle or battle._state.value == "COMPLETED":
                print("戦闘が終了しました")
                break
                
            current_actor = battle.get_current_actor()
            if current_actor.participant_type == ParticipantType.PLAYER:
                # プレイヤーのターン - 基本攻撃を実行
                print(f"プレイヤー{current_actor.entity_id}のターン")
                
                # モンスターをターゲットにして基本攻撃
                monster_states = [state for state in battle.get_combat_states().values() 
                                if state.participant_type == ParticipantType.MONSTER and state.is_alive()]
                
                if monster_states:
                    target_monster = monster_states[0]  # 最初のモンスターをターゲット
                    
                    action_dto = PlayerActionDto(
                        battle_id=battle.battle_id,
                        player_id=current_actor.entity_id,
                        action_id=1,  # 基本攻撃
                        target_ids=[target_monster.entity_id],
                        target_participant_types=[ParticipantType.MONSTER]
                    )
                    
                    battle_service.execute_player_action(battle.battle_id, current_actor.entity_id, action_dto)
                    print(f"プレイヤー{current_actor.entity_id}が基本攻撃を実行")
                else:
                    print("攻撃可能なモンスターがいません")
                    break
            else:
                # モンスターのターンは自動処理される
                print(f"モンスター{current_actor.entity_id}のターン（自動処理）")
            
            # 戦闘終了チェック
            battle_result = battle.check_battle_end_conditions()
            if battle_result:
                print(f"戦闘終了: {battle_result.value}")
                battle_service.end_battle(battle.battle_id)
                break

        print("\n✅ 戦闘デモ完了")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        print("詳細:")
        traceback.print_exc()


def run_unit_tests():
    """基本的な単体テスト"""
    print("=== 単体テスト実行 ===\n")
    
    try:
        # サービス作成テスト
        print("1. サービス作成テスト")
        battle_service = create_sample_battle_service()
        print("✅ BattleApplicationService作成成功\n")
        
        # リポジトリテスト
        print("2. リポジトリテスト")
        player_repo = PlayerRepositoryImpl()
        player = player_repo.find_by_id(1)
        assert player is not None, "プレイヤー1が見つからない"
        assert player.name == "テスト冒険者", f"プレイヤー名が不正: {player.name}"
        print(f"✅ プレイヤー取得成功: {player.name}")
        
        action_repo = ActionRepositoryImpl()
        action = action_repo.find_by_id(1)
        assert action is not None, "アクション1が見つからない"
        assert action.name == "基本攻撃", f"アクション名が不正: {action.name}"
        print(f"✅ アクション取得成功: {action.name}")
        
        area_repo = AreaRepositoryImpl()
        area = area_repo.find_by_spot_id(1)
        assert area is not None, "エリアが見つからない"
        assert area.name == "森林地帯", f"エリア名が不正: {area.name}"
        print(f"✅ エリア取得成功: {area.name}")
        
        monster_repo = MonsterRepositoryImpl()
        monster = monster_repo.find_by_id(1)
        assert monster is not None, "モンスター1が見つからない"
        assert monster.name == "スライム", f"モンスター名が不正: {monster.name}"
        print(f"✅ モンスター取得成功: {monster.name}")
        
        print("\n✅ 全単体テスト成功")
        
    except Exception as e:
        print(f"❌ 単体テストでエラー: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    # 単体テスト実行
    run_unit_tests()
    print("\n" + "="*50 + "\n")
    
    # 戦闘デモ実行
    demo_battle_flow()
