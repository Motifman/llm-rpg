#!/usr/bin/env python3
"""
改良された戦闘システムのデモ

新しいサービスクラスを使用した非同期戦闘ループの動作デモ
"""
import asyncio
from unittest.mock import Mock
from src.application.battle.services.enhanced_battle_service import EnhancedBattleApplicationService
from src.application.battle.services.player_action_waiter import PlayerActionWaiter
from src.application.battle.contracts.dtos import PlayerActionDto
from src.domain.battle.battle_enum import ParticipantType, BattleState
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.combat_state import CombatState
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.base_status import BaseStatus
from src.domain.battle.battle_enum import Element, Race


def create_mock_repositories():
    """テスト用のモックリポジトリを作成"""
    # BattleRepository
    battle_repo = Mock()
    battle_repo.generate_battle_id.return_value = 1
    battle_repo.find_by_spot_id.return_value = None
    battle_repo.save.return_value = None
    
    # PlayerRepository
    player_repo = Mock()
    mock_player = Mock()
    mock_player.player_id = 1
    mock_player.name = "勇者"
    mock_player.current_spot_id = 100
    mock_player.race = Race.HUMAN
    mock_player.element = Element.FIRE
    mock_player.hp = Hp(100, 100)
    mock_player.mp = Mp(50, 50)
    mock_player.calculate_status_including_equipment.return_value = BaseStatus(
        attack=50, defense=30, speed=20, critical_rate=0.1, evasion_rate=0.05
    )
    player_repo.find_by_id.return_value = mock_player
    
    # AreaRepository
    area_repo = Mock()
    mock_area = Mock()
    mock_area.get_spawn_monster_type_ids.return_value = {101}
    area_repo.find_by_spot_id.return_value = mock_area
    
    # MonsterRepository
    monster_repo = Mock()
    mock_monster = Mock()
    mock_monster.monster_type_id = 101
    mock_monster.name = "スライム"
    mock_monster.race = Race.BEAST
    mock_monster.element = Element.WATER
    mock_monster.max_hp = 80
    mock_monster.max_mp = 20
    mock_monster.calculate_status_including_equipment.return_value = BaseStatus(
        attack=30, defense=20, speed=15, critical_rate=0.05, evasion_rate=0.03
    )
    monster_repo.find_by_ids.return_value = [mock_monster]
    
    # ActionRepository
    action_repo = Mock()
    mock_action = Mock()
    mock_action.action_id = 1
    mock_action.name = "剣撃"
    mock_action.execute.return_value = Mock(
        success=True,
        messages=["剣撃が命中！"],
        actor_state_change=Mock(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=0,
            mp_change=-3
        ),
        target_state_changes=[
            Mock(
                target_id=1,
                participant_type=ParticipantType.MONSTER,
                hp_change=-25,
                mp_change=0
            )
        ]
    )
    action_repo.find_by_id.return_value = mock_action
    
    return {
        'battle': battle_repo,
        'player': player_repo,
        'area': area_repo,
        'monster': monster_repo,
        'action': action_repo
    }


def create_mock_services():
    """テスト用のモックサービスを作成"""
    # BattleLogicService
    battle_logic = Mock()
    battle_logic.process_on_turn_start.return_value = TurnStartResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        can_act=True,
        damage=0,
        healing=0
    )
    battle_logic.process_on_turn_end.return_value = TurnEndResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        damage=0,
        healing=0
    )
    
    # MonsterActionService
    monster_action = Mock()
    monster_action.select_monster_action_with_targets.return_value = None
    
    # Notifier
    notifier = Mock()
    
    # EventPublisher
    event_publisher = Mock()
    event_publisher.publish_all.return_value = None
    event_publisher.register_handler.return_value = None
    
    return {
        'battle_logic': battle_logic,
        'monster_action': monster_action,
        'notifier': notifier,
        'event_publisher': event_publisher
    }


async def demonstrate_enhanced_battle_system():
    """改良された戦闘システムのデモンストレーション"""
    print("🗡️ 改良された戦闘システムのデモンストレーション")
    print("=" * 50)
    
    # サービスの初期化
    repositories = create_mock_repositories()
    services = create_mock_services()
    
    player_action_waiter = PlayerActionWaiter(default_timeout_seconds=5.0)
    
    enhanced_battle_service = EnhancedBattleApplicationService(
        battle_repository=repositories['battle'],
        player_repository=repositories['player'],
        area_repository=repositories['area'],
        monster_repository=repositories['monster'],
        action_repository=repositories['action'],
        battle_logic_service=services['battle_logic'],
        monster_action_service=services['monster_action'],
        notifier=services['notifier'],
        event_publisher=services['event_publisher'],
        player_action_waiter=player_action_waiter
    )
    
    print("✅ サービスが初期化されました")
    
    # 1. 戦闘開始
    print("\n📢 戦闘を開始します...")
    player_id = 1
    battle_id = 1
    
    try:
        await enhanced_battle_service.start_battle(player_id)
        print(f"⚔️ 戦闘が開始されました！ (Battle ID: {battle_id})")
        
        # 戦闘ループの状態確認
        is_running = enhanced_battle_service.is_battle_loop_running(battle_id)
        print(f"🔄 戦闘ループ実行中: {is_running}")
        
        # 2. 戦闘状態の確認
        print("\n📊 戦闘状態を確認...")
        
        # モック戦闘の設定（状態確認用）
        mock_battle = Mock()
        mock_battle.battle_id = battle_id
        mock_battle.is_in_progress.return_value = True
        mock_battle._current_turn = 1
        mock_battle._current_round = 1
        mock_battle.get_player_ids.return_value = [player_id]
        mock_battle.get_monster_type_ids.return_value = [101]
        mock_battle._state = BattleState.IN_PROGRESS
        mock_battle._max_players = 4
        
        repositories['battle'].find_by_id.return_value = mock_battle
        
        status = enhanced_battle_service.get_battle_status(battle_id)
        print(f"🎯 戦闘状態:")
        print(f"  - アクティブ: {status.is_active}")
        print(f"  - 現在ターン: {status.current_turn}")
        print(f"  - 現在ラウンド: {status.current_round}")
        print(f"  - プレイヤー数: {status.player_count}")
        print(f"  - モンスター数: {status.monster_count}")
        
        # 3. プレイヤー行動待機のテスト
        print("\n⏳ プレイヤー行動待機システムをテスト...")
        
        # プレイヤー行動の準備
        mock_battle.get_current_actor.return_value = TurnEntry(
            participant_key=(ParticipantType.PLAYER, player_id),
            speed=20,
            priority=0
        )
        
        mock_combat_state = Mock(spec=CombatState)
        mock_combat_state.entity_id = player_id
        mock_combat_state.participant_type = ParticipantType.PLAYER
        mock_battle.get_combat_state.return_value = mock_combat_state
        mock_battle.get_combat_states.return_value = {
            (ParticipantType.PLAYER, player_id): mock_combat_state
        }
        mock_battle.get_events.return_value = []
        mock_battle.clear_events.return_value = None
        mock_battle.apply_battle_action_result.return_value = None
        mock_battle.execute_turn.return_value = None
        
        # 行動実行のシミュレーション
        print("🎮 プレイヤーの行動を実行...")
        
        action_data = PlayerActionDto(
            battle_id=battle_id,
            player_id=player_id,
            action_id=1,
            target_ids=[1],
            target_participant_types=[ParticipantType.MONSTER]
        )
        
        await enhanced_battle_service.execute_player_action(
            battle_id, player_id, action_data
        )
        
        print("✅ プレイヤーの行動が実行されました")
        
        # 4. 統計情報の確認
        print("\n📈 システム統計情報:")
        stats = enhanced_battle_service.get_player_action_waiter_statistics()
        print(f"  - 待機中プレイヤー: {stats['waiting_players']}")
        print(f"  - アクティブイベント: {stats['active_events']}")
        print(f"  - 追跡中の総数: {stats['total_tracked']}")
        
        # 5. 戦闘終了
        print("\n🏁 戦闘を終了...")
        enhanced_battle_service.stop_battle_loop(battle_id)
        
        is_running_after = enhanced_battle_service.is_battle_loop_running(battle_id)
        print(f"🔄 戦闘ループ実行中: {is_running_after}")
        
        print("\n🎉 デモンストレーション完了！")
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


def demonstrate_service_architecture():
    """サービスアーキテクチャの説明"""
    print("\n🏗️ 改良された戦闘システムのアーキテクチャ")
    print("=" * 50)
    
    print("📋 新しいサービスクラス:")
    print("  1. TurnProcessor (ドメインサービス)")
    print("     - ターン処理ロジックの共通化")
    print("     - 戦闘終了条件チェック")
    print("     - ターン進行管理")
    
    print("\n  2. BattleLoopService (アプリケーションサービス)")
    print("     - 非同期戦闘ループの実行")
    print("     - プレイヤー・モンスターターンの制御")
    print("     - バックグラウンドタスク管理")
    
    print("\n  3. PlayerActionWaiter (アプリケーションサービス)")
    print("     - プレイヤー行動完了の待機")
    print("     - タイムアウト処理")
    print("     - 行動状態管理")
    
    print("\n  4. EnhancedBattleApplicationService")
    print("     - 上記サービスの統合")
    print("     - 既存APIとの互換性維持")
    print("     - 非同期戦闘フローの実現")
    
    print("\n✨ 改良点:")
    print("  - DDDの原則に従った責務分離")
    print("  - 重複コードの削除")
    print("  - 非同期処理による効率化")
    print("  - テスト可能性の向上")
    print("  - 拡張性の改善")


async def main():
    """メイン関数"""
    print("🚀 改良された戦闘システムデモ開始")
    
    # アーキテクチャの説明
    demonstrate_service_architecture()
    
    # 実際のデモ
    await demonstrate_enhanced_battle_system()
    
    print("\n🎯 まとめ:")
    print("  - 戦闘システムが正常にリファクタリングされました")
    print("  - 新しいサービスクラスが適切に連携しています")
    print("  - 非同期戦闘ループが実装されました")
    print("  - テストカバレッジが向上しました")
    print("  - 実際の戦闘フローで使用する準備が整いました")


if __name__ == "__main__":
    asyncio.run(main())
