#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
Cursesベースの戦闘システムデモ
curses_battle_ui.pyを使用した戦闘システムのデモンストレーション

新機能:
- Cursesベースのリアルタイム戦闘UI
- 外部入力なしでの自動戦闘デモ
- 視覚的な戦闘状況表示
- アニメーション付きのアクション結果表示
"""
import asyncio
import curses
from typing import List, Dict, Any, Optional
from queue import Queue
from threading import Event

from src.application.battle.services.enhanced_battle_service import EnhancedBattleApplicationService
from src.application.battle.services.player_action_waiter import PlayerActionWaiter
from src.application.battle.contracts.dtos import PlayerActionDto
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

# Curses UI統合システム
from src.application.battle.handlers.enhanced_ui_battle_handler import (
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
from src.presentation.ui.curses_battle_ui import CursesBattleUIManager
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


class CursesBattleDemo:
    """Curses戦闘デモクラス"""
    
    def __init__(self):
        self.ui_manager = None
        self.ui_notifier = None
        self.battle_service = None
        self.battle_repository = None
        self.battle_id = None
        self._is_running = True  # 初期値をTrueに変更
    
    def initialize_services(self):
        """サービスを初期化"""
        # リポジトリの初期化
        player_repository = InMemoryPlayerRepository()
        monster_repository = InMemoryMonsterRepository()
        action_repository = InMemoryActionRepository()
        area_repository = InMemoryAreaRepository()
        battle_repository = InMemoryBattleRepository()
        
        # サービス初期化
        notifier = EnhancedDemoNotifier(show_notifications=False)
        self.ui_notifier = UIBattleNotifier()
        event_publisher = EnhancedDemoEventPublisher(self.ui_notifier)
        
        battle_logic_service = BattleLogicService()
        monster_action_service = MonsterActionService()
        
        self.battle_service = EnhancedBattleApplicationService(
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
        
        self.battle_repository = battle_repository
    
    async def run_battle_demo(self):
        """戦闘デモを実行"""
        try:
            print("🎮 戦闘デモ開始")  # デバッグ用
            # シナリオ1: 戦闘開始
            await self.battle_service.start_battle(1)
            print("🎮 戦闘開始完了")  # デバッグ用
            
            # バトルを取得
            battle = None
            for battle_candidate in self.battle_repository._battles.values():
                if 1 in battle_candidate.get_player_ids():
                    battle = battle_candidate
                    break
            
            if not battle:
                return
            
            self.battle_id = battle.battle_id
            
            # 戦闘開始の確認時間
            await asyncio.sleep(2)
            
            # シナリオ2: プレイヤーアクションのデモ
            demo_actions = [
                PlayerActionDto(
                    battle_id=self.battle_id, 
                    player_id=1, 
                    action_id=1,
                    target_ids=[1],
                    target_participant_types=[ParticipantType.MONSTER]
                ),
                PlayerActionDto(
                    battle_id=self.battle_id, 
                    player_id=1, 
                    action_id=2,
                    target_ids=[2],
                    target_participant_types=[ParticipantType.MONSTER]
                ),
                PlayerActionDto(
                    battle_id=self.battle_id, 
                    player_id=1, 
                    action_id=3,
                    target_ids=[2],
                    target_participant_types=[ParticipantType.MONSTER]
                ),
                PlayerActionDto(
                    battle_id=self.battle_id, 
                    player_id=1, 
                    action_id=6,
                    target_ids=None,
                    target_participant_types=None
                ),
            ]
            
            for i, action_dto in enumerate(demo_actions, 1):
                try:
                    await self.battle_service.execute_player_action(
                        battle_id=action_dto.battle_id,
                        player_id=action_dto.player_id,
                        action_data=action_dto
                    )
                except Exception as e:
                    pass  # エラーは無視して続行
                
                # UI更新の確認時間
                await asyncio.sleep(2)
                
                # 戦闘終了チェック
                updated_battle = self.battle_repository.find_by_id(self.battle_id)
                if updated_battle and not updated_battle.is_in_progress():
                    break
            
            # 最終結果表示時間
            await asyncio.sleep(3)
            
        except Exception as e:
            pass  # エラーは無視


def curses_main(stdscr):
    """Cursesメイン関数"""
    demo = CursesBattleDemo()
    
    # サービスを先に初期化（ui_notifierを作成）
    demo.initialize_services()
    
    # UI管理システムを初期化
    demo.ui_manager = CursesBattleUIManager()
    demo.ui_manager.initialize(demo.ui_notifier, stdscr)
    demo.ui_manager.configure_display(enabled=True, animation_delay=1.0)
    
    # 非同期タスクを実行するためのイベントループ
    async def run_demo():
        try:
            await demo.run_battle_demo()
        except Exception as e:
            print(f"戦闘デモエラー: {e}")
        finally:
            demo._is_running = False
    
    # 非同期タスクを開始
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # デモをバックグラウンドで実行
    import threading
    demo_thread = threading.Thread(target=lambda: loop.run_until_complete(run_demo()))
    demo_thread.daemon = True
    demo_thread.start()
    
    # UIメインループ
    try:
        while demo._is_running:
            if not demo.ui_manager.ui.process_input():
                break
            # 短い待機時間でCPU使用率を下げる
            import time
            time.sleep(0.01)
        
        # 戦闘終了後もUIを維持
        if not demo._is_running:
            # 戦闘終了メッセージを表示
            demo.ui_notifier.add_battle_message("戦闘が終了しました。'q'キーで終了してください。")
            
            # 終了待機ループ
            while True:
                if not demo.ui_manager.ui.process_input():
                    break
                import time
                time.sleep(0.01)
                
    except KeyboardInterrupt:
        pass
    finally:
        demo._is_running = False
        # イベントループをクリーンアップ
        try:
            loop.call_soon_threadsafe(loop.stop)
            loop.close()
        except Exception:
            pass
    # finalize()は呼ばない（curses.wrapperが自動的に処理する）


async def demonstrate_curses_battle_system():
    """Curses戦闘システムのデモ（非同期版）"""
    print("🎮 Curses戦闘システムデモ")
    print("=" * 50)
    print("Curses UIを起動しています...")
    print("戦闘が自動的に進行し、UIがリアルタイムで更新されます。")
    print("'q'キーで終了できます。")
    print("=" * 50)
    
    try:
        # Curses UIを起動
        curses.wrapper(curses_main)
    except Exception as e:
        print(f"❌ デモ実行エラー: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 デモ完了！")
    print("=" * 50)
    print("✨ 実現された機能:")
    print("📊 Cursesベースのリアルタイム戦闘状況表示")
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
    print("📱 Curses UI統合アーキテクチャ")
    print("   - イベント駆動によるリアルタイム更新")
    print("   - 外部入力なしでの自動戦闘デモ")
    print("   - 詳細な戦闘情報の完全な取得・表示")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(demonstrate_curses_battle_system())
