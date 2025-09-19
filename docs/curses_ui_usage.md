# Curses戦闘UI使用ガイド

## 概要

Curses戦闘UIは、Pythonのcursesライブラリを使用して実装された動的な戦闘システムUIです。従来のPseudoBattleUIと比較して、以下の特徴があります：

- **動的更新**: 画面をクリアせずに特定の領域のみを更新
- **リアルタイム表示**: 戦闘状況の変化を即座に反映
- **キーボード操作**: 実際のWebUIやGUIに近い操作感
- **アニメーション効果**: アクション結果の視覚的フィードバック
- **カラー表示**: 状況に応じた色分け表示

## ファイル構成

```
src/presentation/ui/
├── curses_battle_ui.py          # メインのCurses UI実装
├── battle_ui_adapter.py         # 既存システムとの統合アダプター
└── pseudo_battle_ui.py          # 従来のPseudo UI（互換性維持）

demos/battle/
└── demo_curses_battle_system.py # Curses UIデモ

test_curses_ui.py                # 簡単なテストスクリプト
```

## 基本的な使用方法

### 1. 簡単なテスト

```bash
# テストスクリプトを実行
python test_curses_ui.py
```

### 2. デモの実行

```bash
# 完全な戦闘システムデモを実行
python demos/battle/demo_curses_battle_system.py
```

### 3. プログラムでの使用

```python
import curses
from src.presentation.ui.battle_ui_adapter import BattleUIFactory

def main(stdscr):
    # UIアダプターを作成
    ui_adapter = BattleUIFactory.create_curses_ui()
    
    # UI通知システムを作成
    ui_notifier = UIBattleNotifier()
    
    # 初期化
    ui_adapter.initialize(ui_notifier, stdscr)
    ui_adapter.configure_display(enabled=True, animation_delay=0.3)
    
    # 入力コールバックを設定
    def handle_input(command):
        print(f"コマンド: {command}")
        return True
    
    ui_adapter.set_input_callback(handle_input)
    
    # メインループを実行
    ui_adapter.run_main_loop()

# Cursesラッパーで実行
curses.wrapper(main)
```

## UIレイアウト

Curses UIは以下の領域に分割されています：

```
┌─────────────────────────────────────────────────────────────┐
│ ヘッダー領域 (4行)                                          │
│ - 戦闘ID、ラウンド/ターン情報                               │
├─────────────────────────────────────────────────────────────┤
│ 参加者ステータス領域 (12行)                                 │
│ - プレイヤーとモンスターのHP/MPバー                         │
│ - 攻撃力、防御力、速度                                      │
│ - 状態異常・バフ表示                                        │
├─────────────────────────────────────────────────────────────┤
│ ターン情報領域 (4行)                                        │
│ - 現在のアクター                                            │
│ - ターン順序                                                │
├─────────────────────────────────────────────────────────────┤
│ バトルログ領域 (8行)                                        │
│ - 戦闘メッセージ                                            │
│ - アクション結果                                            │
├─────────────────────────────────────────────────────────────┤
│ 入力エリア (3行)                                            │
│ - コマンド入力                                              │
└─────────────────────────────────────────────────────────────┘
```

## 操作方法

### キーボード操作

- **q**: 終了
- **Enter**: コマンド実行
- **Backspace**: 文字削除
- **文字入力**: コマンド入力

### 利用可能なコマンド（デモ版）

- `attack` - 攻撃
- `fireball` - ファイアボール
- `heal` - ヒール
- `help` - ヘルプ表示
- `quit` - 終了

## カラー表示

UIでは以下の色分けが使用されます：

- **ヘッダー**: 青背景、白文字
- **ステータス**: 緑背景、黒文字
- **ログ**: 黒背景、白文字
- **入力**: 黄背景、黒文字
- **HPバー**: 赤背景、白文字
- **MPバー**: 青背景、白文字
- **クリティカル**: 赤背景、白文字
- **回復**: 緑背景、白文字

## アニメーション効果

- **アクション実行**: 中央にアクション名を表示
- **ダメージ/回復**: ターゲットへの効果を表示
- **遅延設定**: `animation_delay`パラメータで調整可能

## 既存システムとの統合

### PseudoBattleUIからの移行

```python
# 従来のPseudo UI
from src.presentation.ui.pseudo_battle_ui import BattleUIManager

# 新しいCurses UI
from src.presentation.ui.battle_ui_adapter import BattleUIFactory

# 互換性のあるインターフェース
ui_adapter = BattleUIFactory.create_curses_ui()  # または create_pseudo_ui()
```

### イベントハンドラーとの連携

Curses UIは既存の`UIBattleNotifier`システムと完全に互換性があります：

```python
# 既存のイベントハンドラーがそのまま使用可能
ui_notifier = UIBattleNotifier()
ui_adapter.initialize(ui_notifier, stdscr)

# イベントハンドラーの登録
notifier.register_handler(EnhancedBattleStartedHandler(ui_notifier))
notifier.register_handler(EnhancedTurnExecutedHandler(ui_notifier))
# ... その他のハンドラー
```

## 設定オプション

### 表示設定

```python
ui_adapter.configure_display(
    enabled=True,           # 表示の有効/無効
    animation_delay=0.3     # アニメーション遅延（秒）
)
```

### レイアウト調整

```python
# UILayoutクラスでレイアウトをカスタマイズ
layout = UILayout(
    header_height=4,        # ヘッダー高さ
    status_height=12,       # ステータス高さ
    log_height=8,          # ログ高さ
    input_height=3,        # 入力高さ
    margin=1               # マージン
)
```

## トラブルシューティング

### 画面サイズエラー

```
RuntimeError: 画面サイズが小さすぎます。最小: 80x20, 現在: 60x15
```

**解決方法**: ターミナルウィンドウを80x20以上にリサイズしてください。

### 色が表示されない

**原因**: ターミナルが色表示をサポートしていない

**解決方法**: 
- カラーターミナルを使用
- `TERM`環境変数を確認
- curses.has_colors()で色サポートを確認

### キー入力が反応しない

**原因**: タイムアウト設定やキーボード設定の問題

**解決方法**:
```python
# タイムアウトを調整
stdscr.timeout(100)  # 100ms

# キーボード設定を確認
stdscr.keypad(True)
```

## パフォーマンス考慮事項

- **更新頻度**: 必要以上に頻繁な更新は避ける
- **アニメーション遅延**: 長すぎると操作感が悪くなる
- **ログサイズ**: 大量のログは表示領域を圧迫する

## 今後の拡張予定

- [ ] マウス操作サポート
- [ ] より高度なアニメーション効果
- [ ] 設定ファイルによるカスタマイズ
- [ ] 複数ウィンドウ対応
- [ ] スクリーンショット機能

## ライセンス

このプロジェクトのライセンスに従います。
