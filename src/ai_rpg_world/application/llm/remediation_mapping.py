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
    "PLACEMENT_SPOT_NOT_FOUND": "プレイヤーの現在地が取得できません。マップ上にいるか確認してください。",
    "TARGET_NOT_FOUND": "指定された対象が視界内にないか、既に去っています。",
    "UNKNOWN_TOOL": "利用可能なツール一覧から選択してください。",
    "TODO_ERROR": "正しい TODO ID または内容を指定してください。",
    "SYSTEM_ERROR": "しばらくしてから再度お試しください。",
    "LLM_API_CALL_FAILED": "LLM API が一時的に利用できません。しばらくしてから再度お試しください。",
    "LLM_RATE_LIMIT": "リクエスト制限に達しました。しばらくしてから再度お試しください。",
    "LLM_AUTHENTICATION_ERROR": "API 認証に失敗しました。設定を確認してください。",
    "LLM_API_KEY_MISSING": "API キーが設定されていません。環境変数または設定を確認してください。",
    "QUEST_ISSUER_NOT_AT_GUILD_LOCATION": "ギルド依頼はギルドのロケーションにいる場合のみ発行できます。ギルドがある場所へ移動してください。",
    "QUEST_GUILD_NOT_FOUND": "指定したギルドが見つかりません。",
    "INVALID_OBJECTIVES": "クエスト目標（objectives）の形式を確認してください。",
    "INVALID_OBJECTIVE_TYPE": "プレイヤー発行可能な目標は kill_monster, obtain_item, reach_spot, kill_player です。",
    "MONSTER_TEMPLATE_NOT_FOUND": "指定したモンスター名が見つかりません。名前を確認してください。",
    "SPOT_NOT_FOUND": "指定したスポット名が見つかりません。名前を確認してください。",
    "ITEM_SPEC_NOT_FOUND": "指定したアイテム名が見つかりません。名前を確認してください。",
    "PLAYER_PROFILE_NOT_FOUND": "指定したプレイヤー名が見つかりません。名前を確認してください。",
    "RESOLVER_NOT_CONFIGURED": "target_name による解決にはリポジトリ設定が必要です。target_id を指定してください。",
    "MISSING_CURRENT_SPOT": "現在地スポットが取得できていません。マップ上にいるか確認してください。",
    "MISSING_CURRENT_AREA": "現在地がロケーションエリアに含まれていません。ギルドはロケーション内で作成してください。",
    "MISSING_GUILD_NAME": "ギルド名を指定してください。",
    "INVALID_ROLE": "役職は leader / officer / member のいずれかを指定してください。",
    # Issue #168 で導入した executor 横断の learnable failure 用 code 群。
    # application/llm/services/failure_helpers.py のファクトリから参照される。
    "INVALID_ARGUMENT": "ツール引数の型 / 必須項目を確認してください。",
    "SNS_REF_STALE": "SNS の ref は世代管理されています。ページを再読込してから ref を取得し直してください。",
    "TRADE_ARG_MISSING": "取引ツールの必須引数 (item_instance_id / slot_id / requested_gold / trade_ref 等) を確認してください。",
    "TRADE_PAGE_NOT_SUPPORTED": "現在の SNS / Trade ページではこの操作は実行できません。対応するページに遷移してください。",
    "ATTACK_PRECONDITION_FAILED": "攻撃の前提条件 (クールダウン / 対象の生死 / 攻撃力など) を確認し、必要なら待機または別行動を選んでください。",
    "INVENTORY_NOT_FOUND": "プレイヤーのインベントリが見つかりません。プレイヤー初期化が完了しているか確認してください。",
    "ITEM_NOT_CONSUMABLE": "そのアイテムは使用 (consume) できません。別のアイテムを指定するか、別ツールで操作してください。",
    "ACTIVE_APP_CONFLICT": "既に別アプリ (SNS / 取引所など) を開いています。exit してから再度 enter してください。",
    "INVALID_DIRECTION": "方向は 北 / 北東 / 東 / 南東 / 南 / 南西 / 西 / 北西 のいずれかを指定してください。",
    "PURSUIT_FAILED": "追跡対象が視界外か既に去っている可能性があります。対象を再確認してください。",
    "PURSUIT_START_FAILED": "追跡対象を確認してください (視界内か / 同じスポットか)。",
    "PURSUIT_CANCEL_FAILED": "追跡中の状態を確認してください。既に中断済みの可能性があります。",
}


def get_remediation(error_code: str) -> str:
    """error_code に対応する対処法を返す。未定義の場合は汎用メッセージ。"""
    if not isinstance(error_code, str):
        raise TypeError("error_code must be str")
    return DEFAULT_REMEDIATION_BY_ERROR_CODE.get(
        error_code,
        "エラー内容を確認し、別の行動を選んでください。",
    )
