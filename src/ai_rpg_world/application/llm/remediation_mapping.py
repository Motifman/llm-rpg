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
    "INVALID_DESTINATION_LABEL": "現在の状況に表示されている移動先ラベルから選択してください。",
    "INVALID_DESTINATION_KIND": "移動先として使えるラベルを選択してください。",
    "INVALID_TARGET_LABEL": "現在の状況に表示されている対象ラベルから選択してください。",
    "INVALID_TARGET_KIND": "そのラベルはこの操作には使えません。対象の種類を確認してください。",
    "INTERACTION_INVALID": "相互作用できる距離や状態か確認し、別の対象を選んでください。",
    "INTERACTION_TARGET_NOT_FOUND": "対象オブジェクトがまだ見えているか確認してください。",
    "ITEM_NOT_FOUND": "指定されたアイテムがインベントリにないか、既に失われています。",
    "NO_ITEM_IN_SLOT": "指定スロットにアイテムがありません。インベントリの状態を確認してください。",
    "ITEM_RESERVED": "そのアイテムは取引中等で予約されています。取引を完了またはキャンセルしてください。",
    "TARGET_NOT_FOUND": "指定された対象が視界内にないか、既に去っています。",
    "UNKNOWN_TOOL": "利用可能なツール一覧から選択してください。",
    "MEMORY_QUERY_DSL_PARSE_ERROR": "DSL 式の形式を確認してください。例: episodic.take(10)",
    "MEMORY_QUERY_DSL_EVAL_ERROR": "DSL 式の評価に失敗しました。変数名と take の引数を確認してください。",
    "MEMORY_QUERY_INVALID_OUTPUT_MODE": "output_mode は text / count / preview / handle のいずれかを指定してください。",
    "SUBAGENT_ERROR": "bindings と query を正しく指定してください。",
    "SUBAGENT_LLM_ERROR": "要約・教訓の取得に失敗しました。しばらくしてから再度お試しください。",
    "TODO_ERROR": "正しい TODO ID または内容を指定してください。",
    "WORKING_MEMORY_ERROR": "追加するテキストを指定してください。",
    "SYSTEM_ERROR": "しばらくしてから再度お試しください。",
    "LLM_API_CALL_FAILED": "LLM API が一時的に利用できません。しばらくしてから再度お試しください。",
    "LLM_RATE_LIMIT": "リクエスト制限に達しました。しばらくしてから再度お試しください。",
    "LLM_AUTHENTICATION_ERROR": "API 認証に失敗しました。設定を確認してください。",
    "LLM_API_KEY_MISSING": "API キーが設定されていません。環境変数または設定を確認してください。",
}


def get_remediation(error_code: str) -> str:
    """error_code に対応する対処法を返す。未定義の場合は汎用メッセージ。"""
    if not isinstance(error_code, str):
        raise TypeError("error_code must be str")
    return DEFAULT_REMEDIATION_BY_ERROR_CODE.get(
        error_code,
        "エラー内容を確認し、別の行動を選んでください。",
    )
