#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
実用的な戦闘システムのデモ v3 (修正版)
改善されたイベントシステムと擬似UIを統合 - エラー修正版

新機能:
- 改善されたバトルイベントシステムの使用
- 擬似的なUI表示システム
- リアルタイムでの戦闘状況表示
- 詳細な参加者ステータス表示
- アニメーション付きのアクション結果表示

修正点:
- メソッド呼び出しの修正
- 戦闘ループの簡略化
- エラーハンドリングの改善
"""
import asyncio
from typing import List, Dict, Any, Optional
from queue import Queue
from threading import Event

from src.application.combat.services.enhanced_battle_service import EnhancedBattleApplicationService
from src.application.combat.services.player_action_waiter import PlayerActionWaiter
from src.application.combat.contracts.dtos import PlayerActionDto
from src.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from src.infrastructure.repository.in_memory_monster_repository import InMemoryMonsterRepository
from src.infrastructure.repository.in_memory_action_repository import InMemoryActionRepository
from src.infrastructure.repository.in_memory_area_repository import InMemoryAreaRepository
from src.infrastructure.repository.in_memory_battle_repository import InMemoryBattleRepository
from src.domain.battle.battle_service import BattleLogicService
from src.domain.battle.services.monster_action_service import MonsterActionService
from src.domain.common.notifier import Notifier
from src.domain.common.event_publisher import EventPublisher
from src.domain.battle.battle_enum import ParticipantType
from src.domain.player.player_enum import Role

# 新しいUI統合システム
from src.application.combat.handlers.enhanced_ui_battle_handler import (
    UIBattleNotifier,
    EnhancedBattleStartedHandler,
    EnhancedRoundStartedHandler,
    EnhancedTurnStartedHandler,
    EnhancedTurnExecutedHandler,
    EnhancedTurnEndedHandler,
    EnhancedBattleEndedHandler,
    EnhancedMonsterDefeatedHandler,
    EnhancedPlayerDefeatedHandler
)
from src.presentation.ui.pseudo_battle_ui import BattleUIManager
from src.domain.battle.events.battle_events import (
    BattleStartedEvent,
    RoundStartedEvent,
    TurnStartedEvent,
    TurnExecutedEvent,
    TurnEndedEvent,
    BattleEndedEvent,
    MonsterDefeatedEvent,
    PlayerDefeatedEvent
)


class EnhancedDemoNotifier(Notifier):
    """改善されたデモ用通知システム"""
    
    def __init__(self, show_notifications: bool = False):
        self.show_notifications = show_notifications
    
    def send_notification(self, recipient_id: int, message: str) -> None:
        """単一の受信者に通知を送信"""
        if self.show_notifications:
            print(f"📢 通知 (to {recipient_id}): {message}")
    
    def send_notification_to_all(self, recipient_ids: List[int], message: str) -> None:
        """複数の受信者に通知を送信"""
        if self.show_notifications:
            print(f"📢 通知 (to {recipient_ids}): {message}")


class EnhancedDemoEventPublisher(EventPublisher):
    """改善されたデモ用イベントパブリッシャー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
        self._handlers = self._setup_ui_handlers()
    
    def _setup_ui_handlers(self):
        """UI統合ハンドラーを設定"""
        return {
            BattleStartedEvent: EnhancedBattleStartedHandler(self._ui_notifier),
            RoundStartedEvent: EnhancedRoundStartedHandler(self._ui_notifier),
            TurnStartedEvent: EnhancedTurnStartedHandler(self._ui_notifier),
            TurnExecutedEvent: EnhancedTurnExecutedHandler(self._ui_notifier),
            TurnEndedEvent: EnhancedTurnEndedHandler(self._ui_notifier),
            BattleEndedEvent: EnhancedBattleEndedHandler(self._ui_notifier),
            MonsterDefeatedEvent: EnhancedMonsterDefeatedHandler(self._ui_notifier),
            PlayerDefeatedEvent: EnhancedPlayerDefeatedHandler(self._ui_notifier),
        }
    
    def register_handler(self, event_type, handler) -> None:
        """イベントハンドラーを登録"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        elif not isinstance(self._handlers[event_type], list):
            self._handlers[event_type] = [self._handlers[event_type]]
        self._handlers[event_type].append(handler)
    
    def publish(self, event) -> None:
        """単一イベントを発行"""
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        
        if not isinstance(handlers, list):
            handlers = [handlers]
        
        for handler in handlers:
            try:
                handler.handle(event)
            except Exception as e:
                print(f"⚠️ イベントハンドラーエラー ({event_type.__name__}): {e}")
    
    def publish_all(self, events: List) -> None:
        """複数イベントを発行"""
        for event in events:
            self.publish(event)


async def demonstrate_enhanced_realistic_battle_system_fixed():
    """改善された実用的戦闘システムのデモ（修正版）"""
    print("🎮 実用的戦闘システム v3 - 改善されたUI統合デモ (修正版)")
    print("=" * 70)
    
    # UI管理システムを初期化
    ui_notifier = UIBattleNotifier()
    ui_manager = BattleUIManager()
    ui_manager.initialize(ui_notifier)
    ui_manager.configure_display(enabled=True, animation_delay=1.5)  # 1.5秒のアニメーション遅延
    
    # リポジトリの初期化
    player_repository = InMemoryPlayerRepository()
    monster_repository = InMemoryMonsterRepository()
    action_repository = InMemoryActionRepository()
    area_repository = InMemoryAreaRepository()
    battle_repository = InMemoryBattleRepository()
    
    # サービス初期化
    notifier = EnhancedDemoNotifier(show_notifications=False)  # UI表示に集中するため通知は無効
    event_publisher = EnhancedDemoEventPublisher(ui_notifier)
    
    battle_logic_service = BattleLogicService()
    monster_action_service = MonsterActionService()
    
    enhanced_battle_service = EnhancedBattleApplicationService(
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
    
    try:
        # シナリオ1: 戦闘開始
        print("📍 シナリオ1: プレイヤー1が戦闘を開始")
        await enhanced_battle_service.start_battle(1)
        
        # バトルを取得
        battle = None
        for battle_candidate in battle_repository._battles.values():
            if 1 in battle_candidate.get_player_ids():
                battle = battle_candidate
                break
        
        if not battle:
            print("❌ 戦闘が見つかりません")
            return
        
        battle_id = battle.battle_id
        print(f"戦闘開始: Battle ID {battle_id}")
        
        # 戦闘開始の確認時間
        await asyncio.sleep(3)
        
        # シナリオ2: プレイヤーアクションのデモ
        print("\n📍 シナリオ2: プレイヤーアクション実行デモ")
        
        # 複数のアクションを実行してUIの更新を確認
        demo_actions = [
            PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=1,
                target_ids=[1],
                target_participant_types=[ParticipantType.MONSTER]
            ),
            PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=2,
                target_ids=[2],
                target_participant_types=[ParticipantType.MONSTER]
            ),
            PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=3,
                target_ids=[2],
                target_participant_types=[ParticipantType.MONSTER]
            ),
            PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=6,
                target_ids=None,
                target_participant_types=None
            ),
        ]
        
        for i, action_dto in enumerate(demo_actions, 1):
            print(f"\n--- アクション {i} ---")
            try:
                await enhanced_battle_service.execute_player_action(
                    battle_id=action_dto.battle_id,
                    player_id=action_dto.player_id,
                    action_data=action_dto
                )
                print(f"✅ アクション{i}実行成功")
            except Exception as e:
                print(f"⚠️ アクション{i}実行エラー: {e}")
            
            # UI更新の確認時間
            await asyncio.sleep(2)
            
            # 戦闘終了チェック
            updated_battle = battle_repository.find_by_id(battle_id)
            if updated_battle and not updated_battle.is_in_progress():
                print("🎉 戦闘が終了しました！")
                break
        
        # シナリオ3: 戦闘状態の確認
        print("\n📍 シナリオ3: 戦闘状態の最終確認")
        try:
            battle_status = enhanced_battle_service.get_battle_status(battle_id)
            print(f"戦闘状態: アクティブ={battle_status.is_active}")
            print(f"現在ターン: {battle_status.current_turn}")
            print(f"現在ラウンド: {battle_status.current_round}")
            print(f"参加プレイヤー数: {battle_status.player_count}")
            print(f"モンスター数: {battle_status.monster_count}")
        except Exception as e:
            print(f"⚠️ 戦闘状態取得エラー: {e}")
        
        # 最終結果表示時間
        await asyncio.sleep(3)
        
        print("\n🎉 デモ完了！")
        print("=" * 70)
        print("✨ 実現された機能:")
        print("📊 リアルタイム戦闘状況表示")
        print("   - 全参加者の詳細ステータス（HP/MP/攻撃力/防御力/速度）")
        print("   - ビジュアルHPバー・MPバーの表示")
        print("   - 現在のアクター表示（⚡マーク）")
        print("   - ターン順序の視覚的表示")
        print("")
        print("🎬 アニメーション機能")
        print("   - アクション結果の段階的表示")
        print("   - ダメージ・回復エフェクト")
        print("   - 状態異常・バフの適用表示")
        print("")
        print("📱 UI統合アーキテクチャ")
        print("   - イベント駆動によるリアルタイム更新")
        print("   - 実際のWebUI/GUIへの容易な置き換え可能")
        print("   - 詳細な戦闘情報の完全な取得・表示")
        print("")
        print("🔧 実装された改善点:")
        print("   - 改善されたバトルイベントシステム")
        print("   - ParticipantInfo構造体による統一データ")
        print("   - UIBattleNotifierによる通知システム")
        print("   - 擬似UIによる視覚的フィードバック")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ デモ実行エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # UI終了処理
        ui_manager.finalize()


if __name__ == "__main__":
    asyncio.run(demonstrate_enhanced_realistic_battle_system_fixed())
