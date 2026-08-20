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
    "INVALID_DESTINATION_LABEL": "「現在の状況」の接続先に表示されているスポット名を destination_label に指定してください。矢印の左側の道や扉の名前ではなく、\"\" で囲まれた行き先名を使ってください。",
    "INVALID_DESTINATION_KIND": "destination_label には移動先として使えるスポット名を指定してください。アイテム名・プレイヤー名・オブジェクト名は移動先には使えません。",
    "INVALID_TARGET_LABEL": "「現在の状況」に表示されている対象の名前を指定してください。名前が \"\" で囲まれている場合は、その中身をそのまま引数に入れてください。",
    "INVALID_TARGET_KIND": "指定した名前はこの操作の対象ではありません。ツール説明と「現在の状況」を確認し、オブジェクト名・所持アイテム名・その場に落ちているものの名前・プレイヤー名・モンスター名のうち、そのツールが要求する名前を指定してください。",
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
    "SNS_PAGE_NOT_SUPPORTED": "現在の SNS ページではこの操作は実行できません。open_page で適切なページに遷移してから再度試してください。",
    "TRADE_ARG_MISSING": "取引ツールの必須引数 (item_instance_id / slot_id / requested_gold / trade_ref 等) を確認してください。",
    "TRADE_PAGE_NOT_SUPPORTED": "現在の SNS / Trade ページではこの操作は実行できません。対応するページに遷移してください。",
    "ATTACK_PRECONDITION_FAILED": "攻撃の前提条件 (クールダウン / 対象の生死 / 攻撃力など) を確認し、必要なら待機または別行動を選んでください。",
    "INVENTORY_NOT_FOUND": "プレイヤーのインベントリが見つかりません。プレイヤー初期化が完了しているか確認してください。",
    "ITEM_NOT_CONSUMABLE": "そのアイテムは食べ物ではないので、食べる行動では使えません。素材や道具は、近くのものに働きかけて使ってください (例: 焚き火跡に火打ち石で着火)。食べるなら所持アイテムの「食料」を選んでください。",
    "ACTIVE_APP_CONFLICT": "既に別アプリ (SNS / 取引所など) を開いています。exit してから再度 enter してください。",
    "INVALID_DIRECTION": "方向は 北 / 北東 / 東 / 南東 / 南 / 南西 / 西 / 北西 のいずれかを指定してください。",
    "PURSUIT_FAILED": "追跡対象が視界外か既に去っている可能性があります。対象を再確認してください。",
    "PURSUIT_START_FAILED": "追跡対象を確認してください (視界内か / 同じスポットか)。",
    "PURSUIT_CANCEL_FAILED": "追跡中の状態を確認してください。既に中断済みの可能性があります。",
    "NOT_WIRED": "本ツールはこの構成では有効になっていません。別の方法を試してください。",
    "ITEM_TRANSFER_FAILED": "アイテムの受け渡しに失敗しました。インベントリ・現在地・対象 instance を確認してください。",
    # PR-α (Y_after_pr639_640 後続): give_item の domain-specific error に
    # 対する remediation。LLM が result_summary の「対処:」欄を読んで
    # 次アクションを選べるよう、具体的な行動を書く。
    "GIVE_ITEM_TARGET_IS_SELF": "自分自身は指定できません。gives 配列の target_player_label に別のプレイヤー名を指定してください。",
    "GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT": "渡したい相手が同じ場所にいません。先に相手のいる場所へ移動してから、または同じ場所にいる別の相手を選んでから再度渡してください。",
    "GIVE_ITEM_TARGET_INVENTORY_FULL": "相手のインベントリが満杯で受け取れません。相手の手が空くのを待つか、別の相手に渡してください。",
    # 経済統合 Phase 2: 人同士の取引。次の一手が違うものを畳まない。
    "TRADE_PARTNER_NOT_HERE": "取引の相手が同じ場所に居ません。相手の居る場所へ移動してから持ちかけてください。",
    "TRADE_ITEM_NOT_OWNED": "差し出すと書いた品を、その数だけ持っていません。数を減らすか、集めてから持ちかけてください。",
    "TRADE_GOLD_NOT_ENOUGH": "差し出すと書いた額を用意できません。額を下げるか、稼いでから持ちかけてください。",
    "TRADE_UNKNOWN_ITEM": "その名前の品はこの世界にありません。名前を確かめてから求めてください。",
    "TRADE_DUPLICATE_OFFER": "その相手へは既に取引を持ちかけています。返事を待つか、流れるのを待ってから持ちかけ直してください。",
    "TRADE_NO_OFFER_FOR_YOU": "あなたに持ちかけられている取引はありません。誰かが持ちかけるのを待つか、自分から持ちかけてください。",
    "TRADE_OFFER_AMBIGUOUS": "自分宛ての申し出が複数あります。offerer_player_label で誰の申し出かを指定してください。",
    "TRADE_ASK_NOT_MET": "求められているものが足りません。申し出は残っているので、集めてから受け直せます。",
    "PLAYER_TRADE_FAILED": "取引が成立しませんでした。相手が同じ場所に居るか、差し出すもの・求められるものを持っているかを確かめてください。",
    # 経済統合 Phase 2: 取引に出している品は使えない。持っていない場合と
    # 次の一手が違う (探しに行く vs 返事を待つ / 取り下げる)。
    "ITEM_OFFERED_IN_TRADE": "その品は取引の提案に出しているため、いまは使えません。相手の返事を待つか、提案を取り下げてから操作してください。",
    # 経済統合 Phase 1: 売買の失敗。原因ごとに「次に何をすれば取引が成立するか」
    # を書く。金の話と品の話と場所の話を混ぜない。
    "MERCHANT_NOT_AT_SPOT": "その商人はこの場所に居ません。『商人:』にその商人の名前が出ている場所へ移動してから取引してください。",
    "MERCHANT_AMBIGUOUS": "同じ品を扱う商人が複数居ます。merchant_label にどちらの商人と取引するかを指定してください (価格は失敗文に出ています)。",
    "BUY_ITEM_NOT_SOLD_HERE": "その商人はその品を売っていません。『商人:』の売りの行に出ている品名を指定するか、その品を扱う商人のところへ移動してください。",
    "SELL_ITEM_NOT_BOUGHT_HERE": "その商人はその品を買い取りません。『商人:』の買いの行に出ている品を売るか、買い取る商人のところへ移動してください。",
    "BUY_ITEM_NOT_ENOUGH_GOLD": "所持金が足りません。個数を減らすか、先に何かを売って所持金を増やしてから買ってください (不足額は失敗文に出ています)。",
    "BUY_ITEM_INVENTORY_FULL": "買った品を入れる空きがありません。個数を減らすか、持ち物を置く・使うなどして空けてから買ってください。",
    "SELL_ITEM_NOT_OWNED": "売ろうとした数だけ持っていません。所持数の範囲で個数を指定するか、先に集めてから売ってください。",
    "MERCHANT_TRADE_FAILED": "取引が成立しませんでした。『商人:』に出ている品名と価格、自分の所持金と持ち物を確認してから、もう一度指定してください。",
    "GIVE_ITEM_TARGET_DEAD": "死亡している相手はアイテムを受け取れません。生存していて同じ場所にいる別の相手を選んでください。",
    "GIVE_ITEM_TARGET_DOWN": "倒れている相手はアイテムを受け取れません。先に相手を助け起こすか、生存して動ける別の相手を選んでください。",
    # PR-ε (Y_after_pr639_640 audit 後続): drop / pickup 系の頻発失敗を汎用
    # ITEM_TRANSFER_FAILED から分離し、LLM が次アクションを判断できる粒度に
    "ITEM_TRANSFER_SLOT_IS_EMPTY": "その名前のアイテムをもう持っていない可能性があります。inspect_target で自分の所持品を確認し、所持品欄に表示されているアイテム名を指定してください。",
    "PICKUP_ITEM_GROUND_ITEM_GONE": "そのアイテムはもう地面にありません。他のプレイヤーが先に拾ったか、あなたの観測が古い可能性があります。周囲を見直すか、別の目的に切り替えてください。",
    "PICKUP_ITEM_SELF_INVENTORY_FULL": "持ち物がいっぱいです。不要なものを 1 つ手放して空きを作ってから、もう一度拾ってください。",
    # PR-γ (Y_after_pr639_640 後続): audit で未登録が発覚した 5 code に
    # 具体的 remediation を追加。汎用フォールバック文言では LLM が
    # 次アクションを取れない。
    "INVALID_STATE": "システムの一時的な整合性違反です。少し tick を進めてから再試行するか、別の tool を選んでください。",
    # 「いま出していない」は「存在しない」と別物。会議が終われば使えるので、
    # 同じ文言にすると二度と試さなくなる。
    "TOOL_NOT_OFFERED_NOW": "その行動はいまの状況では選べません。「利用可能な tool」の一覧に出ているものから選んでください。状況が変われば再び選べるようになります。",
    # prompt 作成後に会議が始まるなど、本人が選んだ後で状況が変わった場合。
    # 一覧外を選んだ TOOL_NOT_OFFERED_NOW と違い、本人の選択を誤り扱いしない。
    "TOOL_BECAME_UNAVAILABLE": "選んだ後に状況が変わりました。現在の「利用可能な tool」を確認し、いま可能な行動を選んでください。",
    "UNSUPPORTED_TOOL": "このツール名は現在の状況では使えません (存在しない / 未配線 / 権限なし)。「利用可能な tool」一覧を確認して別のツールを選んでください。",
    "ATTACK_FAILED": "攻撃が失敗しました。対象モンスターの状態 (瀕死 / 既に死骸 / 逃走) や自分の HP・武器の有無を再確認してください。その場を離れて逃げるのも選択肢です。",
    "EXHAUSTED": "疲労が限界で、移動や争い、物への働きかけのような重い行動は実行できません。休むか、何か食べてから再挑戦してください。",
    "INTERACTION_PRECONDITION_FAILED": "対象オブジェクトの現在の状態が action の前提条件を満たしていません (例: 既に取り尽くした / 既に開けた)。『現在の状況』のオブジェクト行にある state タグを確認し、別の対象・別の action_name を検討してください。",
}


# **ここに engine のツール識別子を書かないこと。**
#
# 対処文はプロンプトに載る。ツール名を名指しすると、そのツールを
# `disabled_tools` で落とした世界で**存在しないツールを勧める**ことになる。
# 実際 GIVE_ITEM_TARGET_DOWN が `tend_to_player` を勧めており、station_drill
# (蘇生の無い世界) で到達する経路だった。
#
# 呼び出し口が 77 か所あるので、ここへ露出判断を渡す形は取らない。#892
# 「engine の語彙をプロンプトに出さない」に沿って、**日本語で何をするかを
# 書く**。ツールの一覧は別途プロンプトに出ているので、識別子を名指しする
# 必要は無い。
#
# 破ると tests/demos/test_disabled_tools_vanish_from_the_prompt.py が落ちる。


def get_remediation(error_code: str) -> str:
    """error_code に対応する対処法を返す。未定義の場合は汎用メッセージ。"""
    if not isinstance(error_code, str):
        raise TypeError("error_code must be str")
    return DEFAULT_REMEDIATION_BY_ERROR_CODE.get(
        error_code,
        "エラー内容を確認し、別の行動を選んでください。",
    )
