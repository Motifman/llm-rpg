"""
ツール実行失敗時の error_code → 対処法（remediation）マッピング。

オーケストレータが例外を捕捉した際、ApplicationException の error_code から
LLM 向けの対処ヒントを取得し、IActionResultStore の result_summary に載せる。
"""

from typing import Dict

# error_code → 対処法の短い文言。オーケストレータで「結果: 失敗。{message} 対処: {remediation}」のように組み立てる。
DEFAULT_REMEDIATION_BY_ERROR_CODE: Dict[str, str] = {
    "PLAYER_NOT_FOUND": "指定したプレイヤーが存在しません。",
    "MAP_NOT_FOUND": "現在地または目的地のマップ情報が見つかりません。",
    "MOVEMENT_FAILED": "現在地にいるか、目的地が接続されているか確認してください。",
    "MOVEMENT_INVALID": "現在地にいるか、目的地が接続されているか確認してください。",
    "INVALID_DESTINATION": "有効な移動先を選んでください。接続先スポット一覧を確認してください。",
    "GATEWAY_OBJECT_NOT_FOUND": "移動先のゲートウェイまたはオブジェクトを確認してください。",
    "GATEWAY_MONSTER_NOT_FOUND": "移動先のゲートウェイを確認してください。",
    "UNKNOWN_TOOL": "利用可能なツール一覧から選択してください。",
    "SYSTEM_ERROR": "しばらくしてから再度お試しください。",
}


def get_remediation(error_code: str) -> str:
    """error_code に対応する対処法を返す。未定義の場合は汎用メッセージ。"""
    if not isinstance(error_code, str):
        raise TypeError("error_code must be str")
    return DEFAULT_REMEDIATION_BY_ERROR_CODE.get(
        error_code,
        "エラー内容を確認し、別の行動を選んでください。",
    )
