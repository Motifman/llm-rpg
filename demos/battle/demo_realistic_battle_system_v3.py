#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
実用的な戦闘システムのデモ v3
改善されたイベントシステムと擬似UIを統合

新機能:
- 改善されたバトルイベントシステムの使用
- 擬似的なUI表示システム
- リアルタイムでの戦闘状況表示
- 詳細な参加者ステータス表示
- アニメーション付きのアクション結果表示

シナリオ:
1. 同じスポットに二人のプレイヤーがいる
2. プレイヤー1が戦闘を開始（UIで戦闘開始を表示）
3. 戦闘ループ内でプレイヤー行動を適切にハンドリング（リアルタイムUI更新）
4. プレイヤー2が戦闘に参加（UI参加者一覧更新）
5. 両プレイヤーで数ターン進行（詳細なターン進行表示）
6. プレイヤー2が戦闘から離脱（UI参加者一覧更新）
7. プレイヤー1の必殺技でモンスター全滅（アニメーション表示）
8. 戦闘終了（結果画面表示）
"""
import asyncio
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

# 新しいUI統合システム
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


class EnhancedDemoPlayerActionController:
    """改善されたデモ用プレイヤー行動制御システム"""
    
    def __init__(self, enhanced_battle_service: EnhancedBattleApplicationService):
        self._enhanced_battle_service = enhanced_battle_service
        self._action_queue: Queue = Queue()
        self._demo_scenario_actions = []
        self._current_action_index = 0
    
    def setup_demo_scenario(self, battle_id: int):
        """デモシナリオの行動を事前設定"""
        self._demo_scenario_actions = [
            # アリスの初期行動（2ラウンド）
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=1,
                target_ids=[1],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # 基本攻撃
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=2,
                target_ids=[1],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # 強攻撃
            
            # ボブ参加後の行動（3-4ラウンド）
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=1,
                target_ids=[2],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # アリス: ゴブリンに基本攻撃
            (battle_id, 2, PlayerActionDto(
                battle_id=battle_id, 
                player_id=2, 
                action_id=1,
                target_ids=[1],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # ボブ: スライムに基本攻撃
            
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=2,
                target_ids=[2],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # アリス: ゴブリンに強攻撃
            (battle_id, 2, PlayerActionDto(
                battle_id=battle_id, 
                player_id=2, 
                action_id=2,
                target_ids=[1],
                target_participant_types=[ParticipantType.MONSTER]
            )),  # ボブ: スライムに強攻撃
            
            # ボブ離脱後のアリス単独行動（5-6ラウンド）
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=3,
                target_ids=[1, 2],
                target_participant_types=[ParticipantType.MONSTER, ParticipantType.MONSTER]
            )),  # アリス: 全体攻撃（必殺技）
            (battle_id, 1, PlayerActionDto(
                battle_id=battle_id, 
                player_id=1, 
                action_id=3,
                target_ids=[1, 2],
                target_participant_types=[ParticipantType.MONSTER, ParticipantType.MONSTER]
            )),  # アリス: 全体攻撃（必殺技）
        ]
    
    def get_next_player_action(self, battle_id: int, player_id: int) -> Optional[PlayerActionDto]:
        """次のプレイヤー行動を取得"""
        # シナリオからの行動を取得
        for scenario_battle_id, scenario_player_id, action_dto in self._demo_scenario_actions[self._current_action_index:]:
            if scenario_battle_id == battle_id and scenario_player_id == player_id:
                # このアクションを消費
                self._current_action_index += 1
                return action_dto
        
        return None
    
    def has_more_actions(self) -> bool:
        """まだ実行していないアクションがあるかチェック"""
        return self._current_action_index < len(self._demo_scenario_actions)


async def demonstrate_enhanced_realistic_battle_system():
    """改善された実用的戦闘システムのデモ"""
    print("🎮 実用的戦闘システム v3 - 改善されたUI統合デモ")
    print("=" * 60)
    
    # UI管理システムを初期化
    ui_notifier = UIBattleNotifier()
    ui_manager = BattleUIManager()
    ui_manager.initialize(ui_notifier)
    ui_manager.configure_display(enabled=True, animation_delay=1.0)  # 1秒のアニメーション遅延
    
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
    
    # プレイヤー行動制御システム
    action_controller = EnhancedDemoPlayerActionController(enhanced_battle_service)
    
    try:
        # シナリオ1: 戦闘開始
        print("📍 シナリオ1: プレイヤー1が戦闘を開始")
        await enhanced_battle_service.start_battle(1)
        # バトルIDを取得（簡易版）
        battle_id = 1  # デモ用の固定ID
        print(f"戦闘開始: Battle ID {battle_id}")
        
        # デモシナリオを設定
        action_controller.setup_demo_scenario(battle_id)
        
        # 戦闘ループ開始
        await asyncio.sleep(2)  # UI表示を確認する時間
        
        # シナリオ2-3: 初期ラウンドでアリス単独行動
        print("\n📍 シナリオ2-3: アリス単独で2ラウンド戦闘")
        for round_num in range(1, 3):
            print(f"\n--- ラウンド {round_num} ---")
            
            # プレイヤーターン処理
            await process_player_turns(enhanced_battle_service, action_controller, battle_id)
            
            # モンスターターン処理  
            await process_monster_turns(enhanced_battle_service, battle_id)
            
            # ラウンド進行
            await enhanced_battle_service.advance_battle_turn(battle_id)
            
            # UI更新の確認時間
            await asyncio.sleep(1)
        
        # シナリオ4: プレイヤー2参加
        print("\n📍 シナリオ4: プレイヤー2（ボブ）が戦闘に参加")
        try:
            enhanced_battle_service.join_battle(battle_id, 2)
            print("ボブが戦闘に参加しました")
        except Exception as e:
            print(f"参加エラー（予想される）: {e}")
        
        await asyncio.sleep(2)  # UI更新確認
        
        # シナリオ5: 両プレイヤーで2ラウンド戦闘
        print("\n📍 シナリオ5: 両プレイヤーで2ラウンド戦闘")
        for round_num in range(3, 5):
            print(f"\n--- ラウンド {round_num} ---")
            
            # プレイヤーターン処理
            await process_player_turns(enhanced_battle_service, action_controller, battle_id)
            
            # モンスターターン処理
            await process_monster_turns(enhanced_battle_service, battle_id)
            
            # ラウンド進行
            await enhanced_battle_service.advance_battle_turn(battle_id)
            
            await asyncio.sleep(1)
        
        # シナリオ6: プレイヤー2離脱
        print("\n📍 シナリオ6: プレイヤー2が戦闘から離脱")
        try:
            enhanced_battle_service.leave_battle(battle_id, 2)
            print("ボブが戦闘から離脱しました")
        except Exception as e:
            print(f"離脱エラー（予想される）: {e}")
        
        await asyncio.sleep(2)  # UI更新確認
        
        # シナリオ7-8: 必殺技でフィニッシュ
        print("\n📍 シナリオ7-8: アリスの必殺技でモンスター全滅")
        for round_num in range(5, 7):
            print(f"\n--- ラウンド {round_num} (フィニッシュ) ---")
            
            # プレイヤーターン処理
            await process_player_turns(enhanced_battle_service, action_controller, battle_id)
            
            # 戦闘終了チェック
            battle = battle_repository.find_by_id(battle_id)
            if battle and not battle.is_in_progress():
                print("戦闘が終了しました！")
                break
            
            # モンスターターン処理
            await process_monster_turns(enhanced_battle_service, battle_id)
            
            # ラウンド進行
            await enhanced_battle_service.advance_battle_turn(battle_id)
            
            await asyncio.sleep(1)
        
        # 最終結果表示
        await asyncio.sleep(3)  # 結果画面表示時間
        
        print("\n🎉 デモ完了！")
        print("改善されたイベントシステムにより、以下の情報がリアルタイムでUIに表示されました：")
        print("- 全参加者の詳細ステータス（HP/MP/攻撃力/防御力/速度）")
        print("- ターン順序とアクター情報")
        print("- アクション結果の詳細（ダメージ/回復/クリティカル/回避）")
        print("- 状態異常・バフの適用と継続時間")
        print("- リアルタイムでの戦況変化")
        print("- アニメーション付きの視覚的フィードバック")
        
    except Exception as e:
        print(f"❌ デモ実行エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # UI終了処理
        ui_manager.finalize()


async def process_player_turns(enhanced_battle_service: EnhancedBattleApplicationService, 
                             action_controller: EnhancedDemoPlayerActionController, 
                             battle_id: int):
    """プレイヤーターンを処理"""
    battle = enhanced_battle_service._battle_repository.find_by_id(battle_id)
    if not battle:
        return
    
    current_actor = battle.get_current_actor()
    if not current_actor:
        return
    
    participant_type, entity_id = current_actor.participant_key
    
    if participant_type == ParticipantType.PLAYER:
        print(f"  プレイヤー{entity_id}のターン")
        
        # デモシナリオから行動を取得
        action_dto = action_controller.get_next_player_action(battle_id, entity_id)
        if action_dto:
            try:
                await enhanced_battle_service.execute_player_action(action_dto)
                print(f"    アクション実行: {action_dto.action_id}")
            except Exception as e:
                print(f"    アクション実行エラー: {e}")
        else:
            print(f"    アクションが見つかりません（スキップ）")
            # ターンスキップ
            await enhanced_battle_service.advance_battle_turn(battle_id)


async def process_monster_turns(enhanced_battle_service: EnhancedBattleApplicationService, 
                              battle_id: int):
    """モンスターターンを処理"""
    battle = enhanced_battle_service._battle_repository.find_by_id(battle_id)
    if not battle:
        return
    
    current_actor = battle.get_current_actor()
    if not current_actor:
        return
    
    participant_type, entity_id = current_actor.participant_key
    
    if participant_type == ParticipantType.MONSTER:
        print(f"  モンスター{entity_id}のターン")
        try:
            await enhanced_battle_service.execute_monster_action(battle_id)
            print(f"    モンスターアクション実行")
        except Exception as e:
            print(f"    モンスターアクション実行エラー: {e}")


if __name__ == "__main__":
    asyncio.run(demonstrate_enhanced_realistic_battle_system())
