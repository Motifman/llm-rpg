"""イベントハンドラ登録のプロファイル（シナリオごとに必要なハンドラの組み合わせ）"""

from enum import Enum


class EventHandlerProfile(str, Enum):
    """登録するイベントハンドラの組み合わせを表すプロファイル"""

    MOVEMENT_ONLY = "movement_only"
    """移動・ゲートウェイ・マップ相互作用のみ（デモ・移動テスト用）"""

    MOVEMENT_COMBAT = "movement_combat"
    """移動 + 戦闘・モンスター行動（世界シミュレーション・戦闘テスト用）"""

    FULL = "full"
    """全ハンドラ（クエスト・ショップ・会話・SNS 等を含む）"""
