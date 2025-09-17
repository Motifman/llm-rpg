#!/usr/bin/env python3
"""
戦闘システムの基本テスト
最小限の動作確認
"""

def test_imports():
    """インポートテスト"""
    print("=== インポートテスト ===")
    
    try:
        # 基本的なインポート
        from src.domain.battle.battle_enum import ActionType, ParticipantType, Element, Race
        print("✅ battle_enum インポート成功")
        
        from src.domain.battle.action_deck import ActionDeck
        from src.domain.battle.action_slot import ActionSlot
        from src.domain.battle.skill_capacity import SkillCapacity
        print("✅ action_deck関連 インポート成功")
        
        from src.domain.player.hp import Hp
        from src.domain.player.mp import Mp
        print("✅ hp/mp インポート成功")
        
        from src.infrastructure.notifier.console_notifier import ConsoleNotifier
        print("✅ notifier インポート成功")
        
        from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
        print("✅ event_publisher インポート成功")
        
        from src.domain.battle.services.monster_action_service import MonsterActionService
        print("✅ monster_action_service インポート成功")
        
        from src.domain.battle.battle_service import BattleLogicService
        print("✅ battle_service インポート成功")
        
        print("\n✅ 全インポートテスト成功")
        
    except Exception as e:
        print(f"❌ インポートエラー: {e}")
        import traceback
        traceback.print_exc()


def test_basic_objects():
    """基本オブジェクトの作成テスト"""
    print("\n=== 基本オブジェクト作成テスト ===")
    
    try:
        from src.domain.battle.action_deck import ActionDeck
        from src.domain.battle.action_slot import ActionSlot
        from src.domain.battle.skill_capacity import SkillCapacity
        from src.domain.player.hp import Hp
        from src.domain.player.mp import Mp
        
        # ActionSlot作成
        action_slot = ActionSlot(1, 1, 1)
        print(f"✅ ActionSlot作成成功: {action_slot}")
        
        # SkillCapacity作成
        capacity = SkillCapacity(10)
        print(f"✅ SkillCapacity作成成功: {capacity}")
        
        # ActionDeck作成
        deck = ActionDeck([action_slot], capacity)
        print(f"✅ ActionDeck作成成功: {deck}")
        
        # HP/MP作成
        hp = Hp(100, 100)
        mp = Mp(50, 50)
        print(f"✅ HP/MP作成成功: HP={hp.value}/{hp.max_hp}, MP={mp.value}/{mp.max_mp}")
        
        print("\n✅ 全基本オブジェクト作成テスト成功")
        
    except Exception as e:
        print(f"❌ オブジェクト作成エラー: {e}")
        import traceback
        traceback.print_exc()


def test_services():
    """サービス作成テスト"""
    print("\n=== サービス作成テスト ===")
    
    try:
        from src.infrastructure.notifier.console_notifier import ConsoleNotifier
        from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
        from src.domain.battle.services.monster_action_service import MonsterActionService
        from src.domain.battle.battle_service import BattleLogicService
        
        # Notifier作成
        notifier = ConsoleNotifier()
        print("✅ ConsoleNotifier作成成功")
        
        # EventPublisher作成
        event_publisher = InMemoryEventPublisher()
        print("✅ InMemoryEventPublisher作成成功")
        
        # MonsterActionService作成
        monster_action_service = MonsterActionService()
        print("✅ MonsterActionService作成成功")
        
        # BattleLogicService作成
        battle_logic_service = BattleLogicService()
        print("✅ BattleLogicService作成成功")
        
        print("\n✅ 全サービス作成テスト成功")
        
    except Exception as e:
        print(f"❌ サービス作成エラー: {e}")
        import traceback
        traceback.print_exc()


def test_repositories():
    """リポジトリ作成テスト"""
    print("\n=== リポジトリ作成テスト ===")
    
    try:
        from src.infrastructure.repository.action_repository_impl import ActionRepositoryImpl
        
        # ActionRepository作成
        action_repo = ActionRepositoryImpl()
        print("✅ ActionRepositoryImpl作成成功")
        
        # アクション取得テスト
        action = action_repo.find_by_id(1)
        if action:
            print(f"✅ アクション取得成功: {action.name}")
        else:
            print("❌ アクション1が見つからない")
        
        print("\n✅ リポジトリテスト成功")
        
    except Exception as e:
        print(f"❌ リポジトリエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_imports()
    test_basic_objects()
    test_services()
    test_repositories()
    print("\n=== 基本テスト完了 ===")
