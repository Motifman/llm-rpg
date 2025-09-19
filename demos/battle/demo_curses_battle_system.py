#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

"""
Cursesベースの戦闘システムデモ
新しいCurses UIを使用した戦闘システムのデモンストレーション

新機能:
- Cursesライブラリを使用した動的UI更新
- 実際のWebUIやGUIに近い操作感
- リアルタイムでの戦闘状況表示
- キーボード入力による操作
- アニメーション効果
"""

import curses
import asyncio
import time
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
    EnhancedPlayerDefeatedHandler,
    EnhancedStatusEffectAppliedHandler,
    EnhancedBuffAppliedHandler,
    EnhancedDamageDealtHandler,
    EnhancedHealingDoneHandler,
    EnhancedCriticalHitHandler,
    EnhancedEvasionHandler,
    EnhancedBlockHandler,
    EnhancedActionExecutedHandler,
    EnhancedMonsterActionSelectedHandler,
    EnhancedPlayerActionSelectedHandler,
    EnhancedTurnOrderDeterminedHandler,
    EnhancedBattleStateUpdatedHandler,
    EnhancedActionResultHandler,
    EnhancedMessageHandler
)

# Curses UIシステム
from src.presentation.ui.battle_ui_adapter import BattleUIFactory


class CursesBattleDemo:
    """Curses戦闘デモクラス"""
    
    def __init__(self):
        self.ui_adapter = None
        self.ui_notifier = None
        self.battle_service = None
        self.player_action_waiter = None
        self._is_running = False
        self._current_battle_id = None
    
    def initialize_services(self):
        """サービスを初期化"""
        # リポジトリの初期化
        player_repository = InMemoryPlayerRepository()
        monster_repository = InMemoryMonsterRepository()
        action_repository = InMemoryActionRepository()
        area_repository = InMemoryAreaRepository()
        battle_repository = InMemoryBattleRepository()
        
        # ドメインサービスの初期化
        battle_logic_service = BattleLogicService()
        monster_action_service = MonsterActionService()
        
        # イベントシステムの初期化
        notifier = Notifier()
        event_publisher = EventPublisher()
        
        # UI通知システムの初期化
        self.ui_notifier = UIBattleNotifier()
        
        # イベントハンドラーの登録
        self._register_event_handlers(notifier, event_publisher)
        
        # アプリケーションサービスの初期化
        self.battle_service = EnhancedBattleApplicationService(
            player_repository=player_repository,
            monster_repository=monster_repository,
            action_repository=action_repository,
            area_repository=area_repository,
            battle_repository=battle_repository,
            battle_logic_service=battle_logic_service,
            monster_action_service=monster_action_service,
            notifier=notifier,
            event_publisher=event_publisher
        )
        
        # プレイヤーアクション待機システムの初期化
        self.player_action_waiter = PlayerActionWaiter()
    
    def _register_event_handlers(self, notifier: Notifier, event_publisher: EventPublisher):
        """イベントハンドラーを登録"""
        # UI通知システムにイベントハンドラーを登録
        handlers = [
            EnhancedBattleStartedHandler(self.ui_notifier),
            EnhancedRoundStartedHandler(self.ui_notifier),
            EnhancedTurnStartedHandler(self.ui_notifier),
            EnhancedTurnExecutedHandler(self.ui_notifier),
            EnhancedTurnEndedHandler(self.ui_notifier),
            EnhancedBattleEndedHandler(self.ui_notifier),
            EnhancedMonsterDefeatedHandler(self.ui_notifier),
            EnhancedPlayerDefeatedHandler(self.ui_notifier),
            EnhancedStatusEffectAppliedHandler(self.ui_notifier),
            EnhancedBuffAppliedHandler(self.ui_notifier),
            EnhancedDamageDealtHandler(self.ui_notifier),
            EnhancedHealingDoneHandler(self.ui_notifier),
            EnhancedCriticalHitHandler(self.ui_notifier),
            EnhancedEvasionHandler(self.ui_notifier),
            EnhancedBlockHandler(self.ui_notifier),
            EnhancedActionExecutedHandler(self.ui_notifier),
            EnhancedMonsterActionSelectedHandler(self.ui_notifier),
            EnhancedPlayerActionSelectedHandler(self.ui_notifier),
            EnhancedTurnOrderDeterminedHandler(self.ui_notifier),
            EnhancedBattleStateUpdatedHandler(self.ui_notifier),
            EnhancedActionResultHandler(self.ui_notifier),
            EnhancedMessageHandler(self.ui_notifier)
        ]
        
        for handler in handlers:
            notifier.register_handler(handler)
    
    def setup_test_data(self):
        """テストデータをセットアップ"""
        # プレイヤーの作成
        player_data = {
            "player_id": 1,
            "name": "勇者",
            "role": Role.WARRIOR,
            "level": 5,
            "current_hp": 100,
            "max_hp": 100,
            "current_mp": 50,
            "max_mp": 50,
            "attack": 25,
            "defense": 15,
            "speed": 20,
            "area_id": 1
        }
        
        # モンスターの作成
        monster_data = {
            "monster_id": 1,
            "name": "スライム",
            "level": 3,
            "current_hp": 60,
            "max_hp": 60,
            "current_mp": 20,
            "max_mp": 20,
            "attack": 15,
            "defense": 8,
            "speed": 12,
            "area_id": 1
        }
        
        # アクションの作成
        actions_data = [
            {
                "action_id": 1,
                "name": "攻撃",
                "description": "基本的な物理攻撃",
                "action_type": "attack",
                "target_type": "enemy",
                "base_damage": 20,
                "mp_cost": 0,
                "level_requirement": 1
            },
            {
                "action_id": 2,
                "name": "ファイアボール",
                "description": "火の魔法攻撃",
                "action_type": "magic",
                "target_type": "enemy",
                "base_damage": 30,
                "mp_cost": 10,
                "level_requirement": 3
            },
            {
                "action_id": 3,
                "name": "ヒール",
                "description": "HPを回復する",
                "action_type": "heal",
                "target_type": "self",
                "base_damage": -25,
                "mp_cost": 15,
                "level_requirement": 2
            }
        ]
        
        # データをリポジトリに保存
        self.battle_service._player_repository.save_from_dict(player_data)
        self.battle_service._monster_repository.save_from_dict(monster_data)
        
        for action_data in actions_data:
            self.battle_service._action_repository.save_from_dict(action_data)
    
    def handle_user_input(self, command: str) -> bool:
        """ユーザー入力を処理"""
        if not self._is_running or not self._current_battle_id:
            return True
        
        try:
            # コマンドの解析
            parts = command.strip().split()
            if not parts:
                return True
            
            cmd = parts[0].lower()
            
            if cmd == "attack":
                # 攻撃コマンド
                action_dto = PlayerActionDto(
                    player_id=1,
                    action_id=1,
                    target_participant_type=ParticipantType.MONSTER,
                    target_entity_id=1
                )
                self.player_action_waiter.set_action(action_dto)
                self.ui_notifier.notify_message("攻撃を実行します！")
                
            elif cmd == "fireball":
                # ファイアボールコマンド
                action_dto = PlayerActionDto(
                    player_id=1,
                    action_id=2,
                    target_participant_type=ParticipantType.MONSTER,
                    target_entity_id=1
                )
                self.player_action_waiter.set_action(action_dto)
                self.ui_notifier.notify_message("ファイアボールを詠唱します！")
                
            elif cmd == "heal":
                # ヒールコマンド
                action_dto = PlayerActionDto(
                    player_id=1,
                    action_id=3,
                    target_participant_type=ParticipantType.PLAYER,
                    target_entity_id=1
                )
                self.player_action_waiter.set_action(action_dto)
                self.ui_notifier.notify_message("ヒールを詠唱します！")
                
            elif cmd == "quit" or cmd == "q":
                # 終了コマンド
                self.ui_notifier.notify_message("戦闘を終了します...")
                return False
                
            elif cmd == "help" or cmd == "h":
                # ヘルプコマンド
                self.ui_notifier.notify_message("利用可能なコマンド:")
                self.ui_notifier.notify_message("  attack - 攻撃")
                self.ui_notifier.notify_message("  fireball - ファイアボール")
                self.ui_notifier.notify_message("  heal - ヒール")
                self.ui_notifier.notify_message("  help - ヘルプ表示")
                self.ui_notifier.notify_message("  quit - 終了")
                
            else:
                self.ui_notifier.notify_message(f"不明なコマンド: {cmd}")
                self.ui_notifier.notify_message("'help' でコマンド一覧を表示")
            
            return True
            
        except Exception as e:
            self.ui_notifier.notify_message(f"コマンド処理エラー: {e}")
            return True
    
    async def run_battle(self):
        """戦闘を実行"""
        try:
            # 戦闘開始
            self.ui_notifier.notify_message("戦闘を開始します...")
            
            battle_result = await self.battle_service.start_battle(
                player_ids=[1],
                monster_ids=[1],
                area_id=1,
                player_action_waiter=self.player_action_waiter
            )
            
            self._current_battle_id = battle_result.battle_id
            self._is_running = True
            
            # 戦闘ループ
            while self._is_running:
                try:
                    # プレイヤーのアクションを待機
                    action = await self.player_action_waiter.wait_for_action(timeout=30.0)
                    
                    if action:
                        # アクションを実行
                        await self.battle_service.execute_player_action(
                            battle_id=self._current_battle_id,
                            action=action
                        )
                    else:
                        # タイムアウト
                        self.ui_notifier.notify_message("タイムアウト: 自動で攻撃を実行します")
                        default_action = PlayerActionDto(
                            player_id=1,
                            action_id=1,
                            target_participant_type=ParticipantType.MONSTER,
                            target_entity_id=1
                        )
                        await self.battle_service.execute_player_action(
                            battle_id=self._current_battle_id,
                            action=default_action
                        )
                    
                    # 戦闘状態をチェック
                    battle = self.battle_service._battle_repository.find_by_id(self._current_battle_id)
                    if not battle or not battle.is_active:
                        self._is_running = False
                        break
                    
                except Exception as e:
                    self.ui_notifier.notify_message(f"戦闘ループエラー: {e}")
                    break
            
            # 戦闘終了
            self.ui_notifier.notify_message("戦闘が終了しました")
            
        except Exception as e:
            self.ui_notifier.notify_message(f"戦闘実行エラー: {e}")
    
    def run_demo(self, stdscr):
        """デモを実行"""
        try:
            # サービスを初期化
            self.initialize_services()
            
            # テストデータをセットアップ
            self.setup_test_data()
            
            # UIアダプターを作成・初期化
            self.ui_adapter = BattleUIFactory.create_curses_ui()
            self.ui_adapter.initialize(self.ui_notifier, stdscr)
            self.ui_adapter.configure_display(enabled=True, animation_delay=0.5)
            self.ui_adapter.set_input_callback(self.handle_user_input)
            
            # 初期メッセージ
            self.ui_notifier.notify_message("Curses戦闘システムデモを開始します")
            self.ui_notifier.notify_message("'help' でコマンド一覧を表示")
            
            # 戦闘を非同期で開始
            import threading
            battle_thread = threading.Thread(target=lambda: asyncio.run(self.run_battle()), daemon=True)
            battle_thread.start()
            
            # UIメインループを実行
            self.ui_adapter.run_main_loop()
            
        except Exception as e:
            # エラー表示
            if self.ui_notifier:
                self.ui_notifier.notify_message(f"デモ実行エラー: {e}")
            else:
                print(f"デモ実行エラー: {e}")
        finally:
            # 終了処理
            self._is_running = False
            if self.ui_adapter:
                self.ui_adapter.finalize()


def main(stdscr):
    """メイン関数"""
    demo = CursesBattleDemo()
    demo.run_demo(stdscr)


if __name__ == "__main__":
    print("Curses戦闘システムデモを開始します...")
    print("画面サイズが80x20以上であることを確認してください")
    print("Enterキーを押して開始...")
    input()
    
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        print("画面サイズが小さすぎる可能性があります")
