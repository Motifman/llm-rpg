#!/usr/bin/env python3
"""
Curses UIの簡単なテストスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import curses
from src.presentation.ui.curses_battle_ui import CursesBattleUI


def test_curses_ui(stdscr):
    """Curses UIのテスト"""
    try:
        ui = CursesBattleUI()
        ui.initialize(stdscr)
    except Exception as e:
        stdscr.addstr(0, 0, f"初期化エラー: {e}")
        stdscr.refresh()
        stdscr.getch()
        return
    
    # テストメッセージ
    ui._battle_log = [
        "戦闘開始！",
        "勇者のターンです",
        "勇者が攻撃！",
        "スライムに25ダメージ！",
        "スライムのターンです",
        "スライムが攻撃！",
        "勇者に15ダメージ！"
    ]
    
    # ダミーの戦闘状態を作成
    from src.application.battle.handlers.enhanced_ui_battle_handler import UIBattleState, ParticipantInfo
    from src.domain.battle.battle_enum import ParticipantType
    
    dummy_state = UIBattleState(
        battle_id=1,
        round_number=1,
        turn_number=3,
        is_battle_active=True,
        current_actor_id=2,
        current_actor_type=ParticipantType.MONSTER,
        turn_order=[(ParticipantType.PLAYER, 1), (ParticipantType.MONSTER, 2)],
        participants=[
            ParticipantInfo(
                entity_id=1,
                participant_type=ParticipantType.PLAYER,
                name="勇者",
                current_hp=85,
                max_hp=100,
                current_mp=40,
                max_mp=50,
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
                name="スライム",
                current_hp=35,
                max_hp=60,
                current_mp=10,
                max_mp=20,
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
    
    ui._current_state = dummy_state
    ui._refresh_display()
    
    # キー入力待ち
    stdscr.addstr(0, 0, "Curses UI テスト - 'q'で終了")
    stdscr.refresh()
    
    while True:
        key = stdscr.getch()
        if key == ord('q') or key == ord('Q'):
            break
        elif key == ord('r') or key == ord('R'):
            # リフレッシュ
            ui._refresh_display()
        elif key == ord('m') or key == ord('M'):
            # メッセージ追加
            ui._battle_log.append("新しいメッセージが追加されました")
            ui._refresh_display()
    
    ui.finalize()


if __name__ == "__main__":
    print("Curses UIテストを開始します...")
    print("画面サイズが80x20以上であることを確認してください")
    print("3秒後に自動開始します...")
    
    import time
    time.sleep(3)
    
    # ターミナル環境をチェック
    import os
    print(f"TERM環境変数: {os.environ.get('TERM', '未設定')}")
    print(f"COLUMNS: {os.environ.get('COLUMNS', '未設定')}")
    print(f"LINES: {os.environ.get('LINES', '未設定')}")
    
    try:
        # より安全な方法でcursesを初期化
        stdscr = curses.initscr()
        try:
            test_curses_ui(stdscr)
        finally:
            curses.endwin()
        print("テストが正常に終了しました")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        print(f"エラータイプ: {type(e)}")
        import traceback
        traceback.print_exc()
        print("画面サイズが小さすぎる可能性があります")
