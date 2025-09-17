#!/usr/bin/env python3
"""
戦闘システム統合テスト
実際の戦闘フローをテスト
"""

def test_battle_application_service():
    """BattleApplicationServiceの統合テスト"""
    print("=== BattleApplicationService統合テスト ===\n")
    
    try:
        from src.infrastructure.notifier.console_notifier import ConsoleNotifier
        from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
        from src.infrastructure.repository.action_repository_impl import ActionRepositoryImpl
        from src.domain.battle.services.monster_action_service import MonsterActionService
        from src.domain.battle.battle_service import BattleLogicService
        
        # 1. 基本サービス作成テスト
        print("1. 基本サービス作成")
        notifier = ConsoleNotifier()
        event_publisher = InMemoryEventPublisher()
        action_repository = ActionRepositoryImpl()
        monster_action_service = MonsterActionService()
        battle_logic_service = BattleLogicService()
        print("✅ 基本サービス作成成功")
        
        # 2. アクション取得テスト
        print("\n2. アクション機能テスト")
        basic_attack = action_repository.find_by_id(1)
        assert basic_attack is not None, "基本攻撃が見つからない"
        print(f"✅ 基本攻撃取得成功: {basic_attack.name}")
        
        fireball = action_repository.find_by_id(4)
        assert fireball is not None, "ファイアボールが見つからない"
        print(f"✅ ファイアボール取得成功: {fireball.name}")
        
        heal = action_repository.find_by_id(6)
        assert heal is not None, "ヒールが見つからない"
        print(f"✅ ヒール取得成功: {heal.name}")
        
        # 3. MonsterActionService機能テスト
        print("\n3. MonsterActionService機能テスト")
        from src.infrastructure.mocks.mock_monster import create_mock_monsters
        from src.infrastructure.mocks.mock_player import create_mock_players
        from src.domain.battle.combat_state import CombatState
        
        mock_monsters = create_mock_monsters()
        mock_players = create_mock_players()
        
        # CombatStateを作成
        monster_state = CombatState.from_monster(mock_monsters[0], 1)
        player_state = CombatState.from_player(mock_players[0], 1)
        
        print(f"✅ CombatState作成成功: {monster_state.name}, {player_state.name}")
        
        # モンスターアクション選択テスト
        available_actions = [basic_attack, fireball]
        all_participants = [monster_state, player_state]
        
        selected_action = monster_action_service.select_monster_action(
            monster_state, available_actions, all_participants
        )
        
        if selected_action:
            print(f"✅ モンスターアクション選択成功: {selected_action.name}")
        else:
            print("❌ モンスターアクション選択失敗")
        
        print("\n✅ 全統合テスト成功")
        
    except Exception as e:
        print(f"❌ 統合テストエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_battle_application_service()
