"""
Cursesベースの戦闘UI
実際のWebUIやGUIに近い動的更新機能を提供
"""

import curses
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from src.domain.common.value_object import Gold, Exp
from src.application.battle.handlers.enhanced_ui_battle_handler import (
    UIBattleState, UIActionResult, ParticipantInfo
)
from src.domain.battle.battle_enum import ParticipantType, BattleResultType


@dataclass
class UILayout:
    """UIレイアウト設定"""
    header_height: int = 4
    status_height: int = 12
    log_height: int = 8
    input_height: int = 3
    margin: int = 1


class CursesBattleUI:
    """Cursesベースの戦闘UI"""
    
    def __init__(self):
        self._current_state: Optional[UIBattleState] = None
        self._battle_log: List[str] = []
        self._display_enabled = True
        self._animation_delay = 0.3
        self._stdscr = None
        self._layout = UILayout()
        self._max_log_lines = 50
        self._current_input = ""
        self._input_callback = None
        self._is_initialized = False
        
        # 色設定
        self._colors = {}
        self._color_pairs = {}
    
    def initialize(self, stdscr) -> None:
        """Curses初期化"""
        self._stdscr = stdscr
        
        try:
            curses.curs_set(0)  # カーソルを非表示
            curses.noecho()  # エコーを無効化
            curses.cbreak()  # 行バッファリングを無効化
            self._stdscr.keypad(True)  # 特殊キーを有効化
            self._stdscr.timeout(100)  # 100msのタイムアウト
            
            # 色の初期化
            self._initialize_colors()
            
            # 画面サイズの取得とレイアウト調整
            self._adjust_layout()
            
            self._is_initialized = True
            self._draw_initial_screen()
            
        except curses.error as e:
            raise RuntimeError(f"Curses初期化エラー: {e}")
    
    def _initialize_colors(self) -> None:
        """色の初期化"""
        if not curses.has_colors():
            return
        
        curses.start_color()
        
        # 基本色の定義
        self._colors = {
            'white': curses.COLOR_WHITE,
            'black': curses.COLOR_BLACK,
            'red': curses.COLOR_RED,
            'green': curses.COLOR_GREEN,
            'blue': curses.COLOR_BLUE,
            'yellow': curses.COLOR_YELLOW,
            'cyan': curses.COLOR_CYAN,
            'magenta': curses.COLOR_MAGENTA
        }
        
        # 色ペアの定義
        self._color_pairs = {
            'normal': curses.color_pair(1),  # 白背景、黒文字
            'header': curses.color_pair(2),  # 青背景、白文字
            'status': curses.color_pair(3),  # 緑背景、黒文字
            'log': curses.color_pair(4),     # 黒背景、白文字
            'input': curses.color_pair(5),   # 黄背景、黒文字
            'hp_bar': curses.color_pair(6),  # 赤背景、白文字
            'mp_bar': curses.color_pair(7),  # 青背景、白文字
            'critical': curses.color_pair(8), # 赤背景、白文字
            'heal': curses.color_pair(9),    # 緑背景、白文字
        }
        
        # 色ペアの初期化
        curses.init_pair(1, self._colors['black'], self._colors['white'])
        curses.init_pair(2, self._colors['white'], self._colors['blue'])
        curses.init_pair(3, self._colors['black'], self._colors['green'])
        curses.init_pair(4, self._colors['white'], self._colors['black'])
        curses.init_pair(5, self._colors['black'], self._colors['yellow'])
        curses.init_pair(6, self._colors['white'], self._colors['red'])
        curses.init_pair(7, self._colors['white'], self._colors['blue'])
        curses.init_pair(8, self._colors['white'], self._colors['red'])
        curses.init_pair(9, self._colors['white'], self._colors['green'])
    
    def _adjust_layout(self) -> None:
        """画面サイズに基づいてレイアウトを調整"""
        if not self._stdscr:
            return
        
        height, width = self._stdscr.getmaxyx()
        
        # 最小サイズチェック
        if height < 20 or width < 80:
            raise RuntimeError(f"画面サイズが小さすぎます。最小: 80x20, 現在: {width}x{height}")
        
        # レイアウトの動的調整
        available_height = height - 2  # マージン分を引く
        self._layout.status_height = min(12, available_height // 2)
        self._layout.log_height = available_height - self._layout.header_height - self._layout.status_height - self._layout.input_height
    
    def set_display_enabled(self, enabled: bool) -> None:
        """表示の有効/無効を設定"""
        self._display_enabled = enabled
    
    def set_animation_delay(self, delay: float) -> None:
        """アニメーション遅延を設定"""
        self._animation_delay = delay
    
    def set_input_callback(self, callback) -> None:
        """入力コールバックを設定"""
        self._input_callback = callback
    
    def handle_ui_update(self, update_type: str, data: Any) -> None:
        """UI更新を処理"""
        if not self._display_enabled or not self._is_initialized:
            return
        
        if update_type == "battle_state":
            self._handle_battle_state_update(data)
        elif update_type == "action_result":
            self._handle_action_result(data)
        elif update_type == "message":
            self._handle_message(data)
        elif update_type == "battle_end":
            self._handle_battle_end(data)
    
    def _handle_battle_state_update(self, battle_state: UIBattleState) -> None:
        """戦闘状態更新を処理"""
        self._current_state = battle_state
        self._refresh_display()
    
    def _handle_action_result(self, action_result: UIActionResult) -> None:
        """アクション結果を処理"""
        if self._current_state:
            self._current_state.participants = action_result.participants_after
        self._show_action_animation(action_result)
        self._refresh_display()
    
    def _handle_message(self, message: str) -> None:
        """メッセージを処理"""
        self._battle_log.append(message)
        if len(self._battle_log) > self._max_log_lines:
            self._battle_log = self._battle_log[-self._max_log_lines:]
        self._refresh_display()
    
    def _handle_battle_end(self, result_data: Dict[str, Any]) -> None:
        """戦闘終了を処理"""
        self._show_battle_result(result_data)
        if self._current_state:
            self._current_state.is_battle_active = False
        self._refresh_display()
    
    def _draw_initial_screen(self) -> None:
        """初期画面を描画"""
        if not self._stdscr:
            return
        
        self._stdscr.clear()
        self._stdscr.border()
        
        # ヘッダー
        self._draw_header("🎮 戦闘システム - Curses UI", "戦闘開始を待機中...")
        
        # 中央にメッセージ
        height, width = self._stdscr.getmaxyx()
        center_y = height // 2
        center_x = width // 2
        
        welcome_msg = "戦闘システムが初期化されました"
        self._stdscr.addstr(center_y, center_x - len(welcome_msg) // 2, welcome_msg)
        
        self._stdscr.refresh()
    
    def _refresh_display(self) -> None:
        """画面を再描画"""
        if not self._display_enabled or not self._current_state or not self._stdscr:
            return
        
        self._stdscr.clear()
        self._stdscr.border()
        
        # 各セクションを描画
        self._draw_header()
        self._draw_participants()
        self._draw_turn_info()
        self._draw_battle_log()
        self._draw_input_area()
        
        self._stdscr.refresh()
    
    def _draw_header(self, title: str = None, subtitle: str = None) -> None:
        """ヘッダーを描画"""
        if not self._stdscr:
            return
        
        if title is None and self._current_state:
            status = "進行中" if self._current_state.is_battle_active else "終了"
            title = f"🎮 戦闘画面 (Battle ID: {self._current_state.battle_id}) - {status}"
            subtitle = f"📅 ラウンド {self._current_state.round_number} / ターン {self._current_state.turn_number}"
        
        if title:
            self._stdscr.addstr(1, 2, title, self._color_pairs.get('header', 0))
        if subtitle:
            self._stdscr.addstr(2, 2, subtitle, self._color_pairs.get('header', 0))
    
    def _draw_participants(self) -> None:
        """参加者情報を描画"""
        if not self._stdscr or not self._current_state or not self._current_state.participants:
            return
        
        start_y = self._layout.header_height + 1
        current_y = start_y
        
        # タイトル
        self._stdscr.addstr(current_y, 2, "👥 参加者ステータス:", self._color_pairs.get('status', 0))
        current_y += 1
        
        # プレイヤーとモンスターを分けて表示
        players = [p for p in self._current_state.participants if p.participant_type == ParticipantType.PLAYER]
        monsters = [p for p in self._current_state.participants if p.participant_type == ParticipantType.MONSTER]
        
        # プレイヤー表示
        for player in players:
            if current_y >= self._layout.header_height + self._layout.status_height:
                break
            current_y = self._draw_participant_status(player, "👤", current_y)
        
        # モンスター表示
        for monster in monsters:
            if current_y >= self._layout.header_height + self._layout.status_height:
                break
            current_y = self._draw_participant_status(monster, "👹", current_y)
    
    def _draw_participant_status(self, participant: ParticipantInfo, icon: str, start_y: int) -> int:
        """個別参加者のステータスを描画"""
        if not self._stdscr:
            return start_y
        
        current_y = start_y
        
        # 現在のアクターかどうかをチェック
        is_current_actor = (
            self._current_state and
            participant.entity_id == self._current_state.current_actor_id and
            participant.participant_type == self._current_state.current_actor_type
        )
        
        # 名前とアクター表示
        name_display = f"{icon} {participant.name}"
        if is_current_actor:
            name_display += " ⚡"
        
        # 色設定（現在のアクターは強調）
        name_color = self._color_pairs.get('critical', 0) if is_current_actor else 0
        
        self._stdscr.addstr(current_y, 4, name_display, name_color)
        current_y += 1
        
        # HPバーの表示
        hp_percentage = participant.current_hp / max(participant.max_hp, 1)
        hp_bar_length = 20
        filled_length = int(hp_bar_length * hp_percentage)
        hp_bar = "█" * filled_length + "░" * (hp_bar_length - filled_length)
        
        hp_text = f"HP: {hp_bar} {participant.current_hp}/{participant.max_hp}"
        self._stdscr.addstr(current_y, 6, hp_text, self._color_pairs.get('hp_bar', 0))
        current_y += 1
        
        # MPバーの表示
        mp_percentage = participant.current_mp / max(participant.max_mp, 1)
        mp_bar_length = 10
        filled_mp_length = int(mp_bar_length * mp_percentage)
        mp_bar = "█" * filled_mp_length + "░" * (mp_bar_length - filled_mp_length)
        
        mp_text = f"MP: {mp_bar} {participant.current_mp}/{participant.max_mp}"
        self._stdscr.addstr(current_y, 6, mp_text, self._color_pairs.get('mp_bar', 0))
        current_y += 1
        
        # ステータス表示
        stats_text = f"ATK:{participant.attack:3d} DEF:{participant.defense:3d} SPD:{participant.speed:3d}"
        self._stdscr.addstr(current_y, 6, stats_text)
        current_y += 1
        
        # 状態異常・バフ表示
        status_icons = []
        if participant.status_effects:
            for effect_type, duration in participant.status_effects.items():
                status_icons.append(f"{effect_type.value}({duration})")
        if participant.buffs:
            for buff_type, (multiplier, duration) in participant.buffs.items():
                status_icons.append(f"{buff_type.value}x{multiplier:.1f}({duration})")
        if participant.is_defending:
            status_icons.append("🛡️防御")
        if not participant.can_act:
            status_icons.append("😵行動不能")
        
        if status_icons:
            status_text = f"状態: {' '.join(status_icons)}"
            self._stdscr.addstr(current_y, 6, status_text)
            current_y += 1
        
        current_y += 1  # 空行
        return current_y
    
    def _draw_turn_info(self) -> None:
        """ターン情報を描画"""
        if not self._stdscr or not self._current_state:
            return
        
        start_y = self._layout.header_height + self._layout.status_height + 1
        
        self._stdscr.addstr(start_y, 2, "🎯 ターン情報:", self._color_pairs.get('status', 0))
        start_y += 1
        
        if self._current_state.current_actor_id is not None:
            actor = next(
                (p for p in self._current_state.participants 
                 if p.entity_id == self._current_state.current_actor_id and 
                    p.participant_type == self._current_state.current_actor_type),
                None
            )
            if actor:
                actor_type = "プレイヤー" if actor.participant_type == ParticipantType.PLAYER else "モンスター"
                actor_text = f"現在のアクター: {actor.name} ({actor_type})"
                self._stdscr.addstr(start_y, 4, actor_text, self._color_pairs.get('critical', 0))
                start_y += 1
        
        # ターン順序表示
        if self._current_state.turn_order:
            turn_order_display = []
            for i, (participant_type, entity_id) in enumerate(self._current_state.turn_order):
                participant = next(
                    (p for p in self._current_state.participants 
                     if p.entity_id == entity_id and p.participant_type == participant_type),
                    None
                )
                name = participant.name if participant else f"ID{entity_id}"
                if (entity_id == self._current_state.current_actor_id and 
                    participant_type == self._current_state.current_actor_type):
                    name = f"[{name}]"  # 現在のアクターを括弧で囲む
                turn_order_display.append(name)
            
            turn_text = f"ターン順序: {' → '.join(turn_order_display)}"
            self._stdscr.addstr(start_y, 4, turn_text)
    
    def _draw_battle_log(self) -> None:
        """バトルログを描画"""
        if not self._stdscr:
            return
        
        start_y = self._layout.header_height + self._layout.status_height + 4
        
        self._stdscr.addstr(start_y, 2, "📜 バトルログ:", self._color_pairs.get('log', 0))
        start_y += 1
        
        if self._battle_log:
            # 最新のログを表示
            max_lines = min(self._layout.log_height - 2, len(self._battle_log))
            recent_logs = self._battle_log[-max_lines:]
            
            for i, log in enumerate(recent_logs):
                if start_y + i >= self._layout.header_height + self._layout.status_height + self._layout.log_height:
                    break
                self._stdscr.addstr(start_y + i, 4, log)
        else:
            self._stdscr.addstr(start_y, 4, "(ログなし)")
    
    def _draw_input_area(self) -> None:
        """入力エリアを描画"""
        if not self._stdscr:
            return
        
        height, width = self._stdscr.getmaxyx()
        input_y = height - self._layout.input_height
        
        # 入力エリアの背景
        for y in range(input_y, height - 1):
            self._stdscr.addstr(y, 1, " " * (width - 2), self._color_pairs.get('input', 0))
        
        # プロンプト
        prompt = "コマンド: "
        self._stdscr.addstr(input_y, 2, prompt, self._color_pairs.get('input', 0))
        
        # 現在の入力
        if self._current_input:
            self._stdscr.addstr(input_y, 2 + len(prompt), self._current_input)
    
    def _show_action_animation(self, action_result: UIActionResult) -> None:
        """アクション結果のアニメーション表示"""
        if not self._display_enabled or not self._stdscr:
            return
        
        # アニメーション用の一時的な表示
        height, width = self._stdscr.getmaxyx()
        center_y = height // 2
        center_x = width // 2
        
        # アクション実行の表示
        if action_result.action_info:
            action_text = f"{action_result.actor_info.name} が {action_result.action_info.name} を使用！"
            self._stdscr.addstr(center_y, center_x - len(action_text) // 2, action_text, 
                              self._color_pairs.get('critical', 0))
            self._stdscr.refresh()
            time.sleep(self._animation_delay)
        
        # ターゲットへの効果表示
        for target_result in action_result.target_results:
            target = next(
                (p for p in action_result.participants_after 
                 if p.entity_id == target_result.target_id and 
                    p.participant_type == target_result.target_participant_type),
                None
            )
            target_name = target.name if target else f"ID{target_result.target_id}"
            
            effects = []
            if target_result.damage_dealt > 0:
                crit_text = " (クリティカル!)" if target_result.was_critical else ""
                effects.append(f"{target_result.damage_dealt}ダメージ{crit_text}")
            if target_result.healing_done > 0:
                effects.append(f"{target_result.healing_done}回復")
            if target_result.was_evaded:
                effects.append("回避!")
            if target_result.was_blocked:
                effects.append("ブロック!")
            
            if effects:
                effect_text = f"→ {target_name}: {', '.join(effects)}"
                self._stdscr.addstr(center_y + 1, center_x - len(effect_text) // 2, effect_text,
                                  self._color_pairs.get('heal' if target_result.healing_done > 0 else 'critical', 0))
                self._stdscr.refresh()
                time.sleep(self._animation_delay)
    
    def _show_battle_result(self, result_data: Dict[str, Any]) -> None:
        """戦闘結果を表示"""
        if not self._stdscr:
            return
        
        # 結果画面を全画面で表示
        self._stdscr.clear()
        self._stdscr.border()
        
        height, width = self._stdscr.getmaxyx()
        center_y = height // 2
        center_x = width // 2
        
        # 結果表示
        result_type = result_data.get("result_type")
        
        if result_type == BattleResultType.VICTORY:
            result_text = "🎉 勝利！"
            color = self._color_pairs.get('heal', 0)
        elif result_type == BattleResultType.DEFEAT:
            result_text = "💀 敗北..."
            color = self._color_pairs.get('critical', 0)
        elif result_type == BattleResultType.DRAW:
            result_text = "🤝 引き分け"
            color = self._color_pairs.get('normal', 0)
        else:
            result_text = "🤝 不明な結果"
            color = self._color_pairs.get('normal', 0)
        
        self._stdscr.addstr(center_y - 2, center_x - len(result_text) // 2, result_text, color)
        
        # 統計情報
        stats_text = f"ラウンド数: {result_data.get('total_rounds', 0)} / ターン数: {result_data.get('total_turns', 0)}"
        self._stdscr.addstr(center_y, center_x - len(stats_text) // 2, stats_text)
        
        # 続行メッセージ
        continue_text = "何かキーを押してください..."
        self._stdscr.addstr(center_y + 2, center_x - len(continue_text) // 2, continue_text)
        
        self._stdscr.refresh()
        
        # キー入力待ち
        self._stdscr.getch()
    
    def process_input(self) -> bool:
        """入力処理（メインループで呼び出し）"""
        if not self._stdscr or not self._is_initialized:
            return True
        
        try:
            key = self._stdscr.getch()
            
            if key == -1:  # タイムアウト
                return True
            
            if key == ord('q') or key == ord('Q'):
                return False  # 終了
            
            if key == curses.KEY_ENTER or key == ord('\n'):
                if self._input_callback and self._current_input:
                    self._input_callback(self._current_input)
                self._current_input = ""
                self._refresh_display()
            elif key == curses.KEY_BACKSPACE or key == 127:
                if self._current_input:
                    self._current_input = self._current_input[:-1]
                    self._refresh_display()
            elif 32 <= key <= 126:  # 印刷可能文字
                self._current_input += chr(key)
                self._refresh_display()
            
            return True
            
        except curses.error:
            return True
    
    def finalize(self) -> None:
        """UI終了処理"""
        if self._is_initialized:
            try:
                if self._stdscr:
                    self._stdscr.keypad(False)
                curses.nocbreak()
                curses.echo()
                curses.curs_set(1)  # カーソルを表示に戻す
                curses.endwin()
            except curses.error:
                # cursesが既に終了している場合は無視
                pass
            except Exception:
                # その他のエラーも無視
                pass
            finally:
                self._is_initialized = False
                self._stdscr = None


class CursesBattleUIManager:
    """Curses戦闘UI管理クラス"""
    
    def __init__(self):
        self.ui = CursesBattleUI()
        self._is_initialized = False
    
    def initialize(self, ui_notifier, stdscr) -> None:
        """UI通知システムと連携を初期化"""
        if not self._is_initialized:
            self.ui.initialize(stdscr)
            ui_notifier.register_ui_callback(self.ui.handle_ui_update)
            self._is_initialized = True
    
    def configure_display(self, enabled: bool = True, animation_delay: float = 0.3) -> None:
        """表示設定を構成"""
        self.ui.set_display_enabled(enabled)
        self.ui.set_animation_delay(animation_delay)
    
    def set_input_callback(self, callback) -> None:
        """入力コールバックを設定"""
        self.ui.set_input_callback(callback)
    
    def run_main_loop(self) -> None:
        """メインループを実行"""
        if not self._is_initialized:
            return
        
        try:
            while self.ui.process_input():
                time.sleep(0.01)  # CPU使用率を下げる
        except KeyboardInterrupt:
            pass
        finally:
            self.finalize()
    
    def finalize(self) -> None:
        """UI終了処理"""
        if self._is_initialized:
            self.ui.finalize()
            self._is_initialized = False


def main(stdscr):
    """Cursesメイン関数（テスト用）"""
    ui_manager = CursesBattleUIManager()
    
    # ダミーのUI通知システム
    class DummyUINotifier:
        def __init__(self):
            self.callbacks = []
        
        def register_ui_callback(self, callback):
            self.callbacks.append(callback)
        
        def notify(self, update_type, data):
            for callback in self.callbacks:
                callback(update_type, data)
    
    notifier = DummyUINotifier()
    ui_manager.initialize(notifier, stdscr)
    
    # ダミーデータでテスト
    time.sleep(1)
    
    # ダミーの戦闘状態
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
                name="テストプレイヤー",
                current_hp=80,
                max_hp=100,
                current_mp=50,
                max_mp=60,
                attack=25,
                defense=15,
                speed=20,
                status_effects={},
                buffs={},
                is_defending=False,
                can_act=True
            ),
            ParticipantInfo(
                entity_id=2,
                participant_type=ParticipantType.MONSTER,
                name="テストモンスター",
                current_hp=60,
                max_hp=80,
                current_mp=30,
                max_mp=40,
                attack=20,
                defense=10,
                speed=15,
                status_effects={},
                buffs={},
                is_defending=False,
                can_act=True
            )
        ]
    )
    
    notifier.notify("battle_state", dummy_state)
    notifier.notify("message", "戦闘開始！")
    notifier.notify("message", "テストプレイヤーのターンです")
    
    # メインループ
    ui_manager.run_main_loop()


if __name__ == "__main__":
    curses.wrapper(main)
