"""
戦闘UIアダプター
既存の戦闘システムと新しいCursesUIを統合するためのアダプター
"""

import curses
import threading
import time
from typing import Optional, Callable, Any
from src.presentation.ui.curses_battle_ui import CursesBattleUIManager
from src.presentation.ui.pseudo_battle_ui import PseudoBattleUI, BattleUIManager
from src.application.battle.handlers.enhanced_ui_battle_handler import UIBattleNotifier


class BattleUIAdapter:
    """戦闘UIアダプター - 既存システムと新しいUIを統合"""
    
    def __init__(self, ui_type: str = "curses"):
        """
        Args:
            ui_type: UIタイプ ("curses" または "pseudo")
        """
        self.ui_type = ui_type
        self.ui_manager: Optional[Any] = None
        self.ui_notifier: Optional[UIBattleNotifier] = None
        self._is_initialized = False
        self._input_thread: Optional[threading.Thread] = None
        self._should_stop = False
        self._input_callback: Optional[Callable] = None
    
    def initialize(self, ui_notifier: UIBattleNotifier, stdscr=None) -> None:
        """UI初期化"""
        self.ui_notifier = ui_notifier
        
        if self.ui_type == "curses":
            if stdscr is None:
                raise ValueError("Curses UIを使用する場合はstdscrが必要です")
            self.ui_manager = CursesBattleUIManager()
            self.ui_manager.initialize(ui_notifier, stdscr)
        else:
            self.ui_manager = BattleUIManager()
            self.ui_manager.initialize(ui_notifier)
        
        self._is_initialized = True
    
    def configure_display(self, enabled: bool = True, animation_delay: float = 0.3) -> None:
        """表示設定を構成"""
        if not self._is_initialized or not self.ui_manager:
            return
        
        if self.ui_type == "curses":
            self.ui_manager.configure_display(enabled, animation_delay)
        else:
            self.ui_manager.configure_display(enabled, animation_delay)
    
    def set_input_callback(self, callback: Callable) -> None:
        """入力コールバックを設定"""
        self._input_callback = callback
        
        if self.ui_type == "curses" and self.ui_manager:
            self.ui_manager.set_input_callback(callback)
    
    def start_input_thread(self) -> None:
        """入力処理スレッドを開始（Curses UI用）"""
        if self.ui_type != "curses" or not self._is_initialized:
            return
        
        self._should_stop = False
        self._input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self._input_thread.start()
    
    def stop_input_thread(self) -> None:
        """入力処理スレッドを停止"""
        self._should_stop = True
        if self._input_thread and self._input_thread.is_alive():
            self._input_thread.join(timeout=1.0)
    
    def _input_loop(self) -> None:
        """入力処理ループ（別スレッドで実行）"""
        if not self.ui_manager or self.ui_type != "curses":
            return
        
        try:
            while not self._should_stop:
                if hasattr(self.ui_manager.ui, 'process_input'):
                    if not self.ui_manager.ui.process_input():
                        break
                time.sleep(0.01)
        except Exception as e:
            print(f"入力処理エラー: {e}")
    
    def run_main_loop(self) -> None:
        """メインループを実行"""
        if not self._is_initialized or not self.ui_manager:
            return
        
        if self.ui_type == "curses":
            self.ui_manager.run_main_loop()
        else:
            # Pseudo UIの場合は何もしない（既存の動作を維持）
            pass
    
    def finalize(self) -> None:
        """UI終了処理"""
        if self._is_initialized:
            self.stop_input_thread()
            if self.ui_manager:
                self.ui_manager.finalize()
            self._is_initialized = False


class BattleUIFactory:
    """戦闘UIファクトリー"""
    
    @staticmethod
    def create_ui(ui_type: str = "curses") -> BattleUIAdapter:
        """UIアダプターを作成"""
        return BattleUIAdapter(ui_type)
    
    @staticmethod
    def create_curses_ui() -> BattleUIAdapter:
        """Curses UIアダプターを作成"""
        return BattleUIAdapter("curses")
    
    @staticmethod
    def create_pseudo_ui() -> BattleUIAdapter:
        """Pseudo UIアダプターを作成"""
        return BattleUIAdapter("pseudo")


def curses_main(stdscr):
    """Cursesメイン関数（統合テスト用）"""
    from src.application.battle.handlers.enhanced_ui_battle_handler import UIBattleNotifier
    
    # UI通知システムを作成
    ui_notifier = UIBattleNotifier()
    
    # Curses UIアダプターを作成
    ui_adapter = BattleUIFactory.create_curses_ui()
    ui_adapter.initialize(ui_notifier, stdscr)
    ui_adapter.configure_display(enabled=True, animation_delay=0.3)
    
    # 入力コールバックを設定
    def handle_input(command: str):
        print(f"コマンド受信: {command}")
        if command.lower() == "quit":
            return False
        return True
    
    ui_adapter.set_input_callback(handle_input)
    
    # ダミーデータでテスト
    time.sleep(1)
    
    # ダミーの戦闘状態を作成
    from src.application.battle.handlers.enhanced_ui_battle_handler import UIBattleState, ParticipantInfo
    from src.domain.battle.battle_enum import ParticipantType
    
    dummy_state = UIBattleState(
        battle_id=1,
        round_number=1,
        turn_number=1,
        is_battle_active=True,
        current_actor_id=1,
        current_actor_type=ParticipantType.PLAYER,
        turn_order=[(ParticipantType.PLAYER, 1), (ParticipantType.MONSTER, 2)],
        participants=[
            ParticipantInfo(
                entity_id=1,
                participant_type=ParticipantType.PLAYER,
                name="勇者",
                current_hp=95,
                max_hp=100,
                current_mp=60,
                max_mp=80,
                attack=30,
                defense=20,
                speed=25,
                status_effects={},
                buffs={},
                is_defending=False,
                can_act=True
            ),
            ParticipantInfo(
                entity_id=2,
                participant_type=ParticipantType.MONSTER,
                name="スライム",
                current_hp=45,
                max_hp=60,
                current_mp=20,
                max_mp=30,
                attack=15,
                defense=8,
                speed=12,
                status_effects={},
                buffs={},
                is_defending=False,
                can_act=True
            )
        ]
    )
    
    # 戦闘状態を通知
    ui_notifier.notify_battle_state_update(dummy_state)
    ui_notifier.notify_message("戦闘開始！")
    ui_notifier.notify_message("勇者のターンです")
    
    # アニメーション効果のテスト
    time.sleep(2)
    ui_notifier.notify_message("勇者が攻撃！")
    
    # ダミーのアクション結果
    from src.application.battle.handlers.enhanced_ui_battle_handler import UIActionResult, UIActionInfo, UITargetResult
    
    dummy_action_info = UIActionInfo(
        action_id=1,
        name="ファイアボール",
        description="火の魔法攻撃"
    )
    
    dummy_target_result = UITargetResult(
        target_id=2,
        target_participant_type=ParticipantType.MONSTER,
        damage_dealt=25,
        healing_done=0,
        was_critical=False,
        was_evaded=False,
        was_blocked=False
    )
    
    dummy_action_result = UIActionResult(
        actor_info=dummy_state.participants[0],
        action_info=dummy_action_info,
        target_results=[dummy_target_result],
        participants_after=dummy_state.participants,
        status_effects_applied=[],
        buffs_applied=[]
    )
    
    ui_notifier.notify_action_result(dummy_action_result)
    
    # メインループを実行
    ui_adapter.run_main_loop()
    
    # 終了処理
    ui_adapter.finalize()


if __name__ == "__main__":
    curses.wrapper(curses_main)
