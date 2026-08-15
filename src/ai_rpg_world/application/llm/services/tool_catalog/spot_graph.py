"""スポットグラフ用 LLM ツール定義"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.spot_graph_availability_resolvers import (
    SpotGraphToolsAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.tool_catalog.inner_thought import (
    inner_thought_property,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

# speech tool で受け付ける channel 値 (SpeechChannel と 1:1 対応)
SPEECH_CHANNEL_WHISPER = "whisper"
SPEECH_CHANNEL_SAY = "say"
SPEECH_CHANNEL_SHOUT = "shout"
SPEECH_CHANNEL_VALUES = (SPEECH_CHANNEL_WHISPER, SPEECH_CHANNEL_SAY, SPEECH_CHANNEL_SHOUT)

_RESOLVER = SpotGraphToolsAvailabilityResolver()
_IT = inner_thought_property()
# 実験 #29 後続: 行動ツールで報告・段取り・呼びかけを任意で同時発話
# できるようにする。同 spot + 隣接 spot に届く SAY 相当。
from ai_rpg_world.application.llm.services.tool_catalog.say_inline import (
    say_inline_property,
)
_SAY = say_inline_property()

TRAVEL_TO_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    description=(
        "スポットグラフ上で、指定した接続先へ移動を開始する（経路は最短・通行条件を満たす必要がある）。"
        "移動しながら仲間へ報告・呼びかけをしたい場合は say_inline に一言を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "destination_label": {
                "type": "string",
                "description": (
                    "行き先スポットの名前 (例: 入口広間)。"
                    "『現在の状況』の接続先 section では "
                    "``- 扉 → \"館長書斎\"（通行可）`` のように、"
                    "渡すべき spot 名のみが ``\"\"`` で囲まれて表示される。"
                    "**``\"\"`` 内の値をそのまま渡すこと** (quote 記号は剥がして"
                    "中身だけ、または quote ごとどちらでも resolver が解釈する)。"
                    "矢印の左側 (= 道や扉の名前) は渡さない。"
                    "同名スポットが複数ある場合 (まれ) は ``#1`` / ``#2`` の"
                    "ordinal を含めて指定する (例: 小部屋 #2)。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["destination_label", "inner_thought"],
    },
)

SET_SUB_LOCATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    description="現在のスポット内のサブロケーションを変更する。",
    parameters={
        "type": "object",
        "properties": {
            "sub_location_label": {
                "type": "string",
                "description": (
                    "サブロケーションの名前 (例: \"祭壇前\")。同名衝突時は"
                    "``#N`` ordinal を含めて指定。未指定でクリア。"
                ),
            },
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)

EXPLORE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
    description=(
        "現在のスポットを探索する（発見・ドロップ等はシナリオ依存）。"
        "探索しながら発見状況や方針を仲間へ伝えたい場合は say_inline に一言を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)

INTERACT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_INTERACT,
    description=(
        "現在のスポット内のオブジェクトに対し、指定した操作名で相互作用する。"
        "各 action には前提条件 (object の状態など) があり、満たさない場合は "
        "``INTERACTION_PRECONDITION_FAILED`` で失敗する "
        "(例: 一度取り尽くした場所をもう一度漁る / 既に開けた箱をまた開ける)。"
        "利用可能な action_name と現在の object 状態は『現在の状況』section の"
        "各オブジェクト行に出ているので、そこから読み取って渡すこと。"
        "追加入力を要求する action では、各オブジェクト行の action 候補に"
        "必要なキーが『text が要る』のように表示されるため、そのキーを parameters に指定する。"
        "物を触りながら同 spot の他者へ短く声をかけたい場合は say_inline に"
        "一言を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            # 引数名が ``object_label`` ではなく種別中立な ``target_label`` なのは、
            # 対人 interaction (docs/memory_system/interpersonal_interaction_design.md
            # §3.3) で対象が物体だけではなくなるため。引数名は LLM から見て
            # 「何を渡せるか」の広告そのものなので、種別を足す前に名前を先に
            # 中立化しておく。現時点で解決できるのは引き続き物体だけ。
            "target_label": {
                "type": "string",
                "description": (
                    "対象の名前。『現在の状況』の対象行で、"
                    "渡すべき名前のみが ``\"\"`` で囲まれて表示される。"
                    "**``\"\"`` 内の値をそのまま渡すこと** (quote 記号は剥がして"
                    "中身だけ、または quote ごとどちらでも resolver が解釈する)。"
                    "同名衝突時は、表示された番号も名前に含める。"
                ),
            },
            "action_name": {
                "type": "string",
                "description": (
                    "対象に定義された action_name。"
                    "『現在の状況』の対象行にある「使える操作」から、"
                    "``\"\"`` で囲まれた値をそのまま 1 つ選んで渡す。"
                    "表示名へ言い換えたり、表示に無い名前を推測したりしないこと。"
                ),
            },
            "parameters": {
                "type": "object",
                "description": (
                    "action が要求する追加入力。必要なキーは『現在の状況』の action 候補に"
                    "『text が要る』のように表示される（例: {\"text\": \"山頂へ向かった\"}）。"
                    "必要なキーが表示されない action では省略できる。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["target_label", "action_name", "inner_thought"],
    },
)

WAIT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_WAIT,
    description=(
        "その場で短く待機し、時間経過に伴う環境変化や出来事を観測する。"
        "留まりながら仲間へ報告・相談・呼びかけをしたい場合は say_inline に一言を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "待機する理由（任意）。",
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)


# Issue #264 後続: 旧 SAY/WHISPER の 2 tool を廃止し、channel 引数を持つ
# 単一 speech_speak tool に統合した (SHOUT も同時に LLM へ公開)。
#
# channel ごとの到達範囲:
#   - whisper: 同じスポット内の特定 1 人だけ (target_label 必須)
#   - say: 同じスポット + 隣接スポット (1 hop)
#   - shout: 同じスポット + 隣接 + さらに 1 hop 先 (2 hop)
#
# target_label は whisper のときだけ必須。required からは外し、executor で
# validation する (JSON Schema の conditional required は小型 LLM で扱いが
# 不安定なため)。
SPEECH_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPEECH,
    description=(
        "周囲に向けて発話する。channel で音量と到達範囲を選ぶ:\n"
        "- whisper: 同じスポット内の特定 1 人にだけ届く (target_label 必須)\n"
        "- say: 同じスポットと隣接スポット (1 hop) に届く (通常会話)\n"
        "- shout: 同じスポット + 隣接 + さらに 1 hop 先 (2 hop) まで届く (大声で叫ぶ)\n"
        "このツールは発話だけに 1 手を使う。同じ場所より遠くへ届かせたい "
        "(shout) / 1 人にだけ内密に伝えたい (whisper) / 行動に添えるには"
        "長すぎる話をしたいときに使う。ふだんの報告・段取り・呼びかけは、"
        "何かの行動の say_inline に添える方が同じ時間で行動も進むため、"
        "そちらを優先する。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "enum": list(SPEECH_CHANNEL_VALUES),
                "description": (
                    "音量: whisper=同 spot 内 1 人 / say=隣接まで / shout=2 hop まで。"
                    "範囲が広いほど多くの人に届くが、敵などにも聞かれるリスクが上がる。"
                ),
            },
            "content": {
                "type": "string",
                "description": "発話内容。",
            },
            "target_label": {
                "type": "string",
                "description": (
                    "channel=whisper のときのみ必須。同じ場所にいるプレイヤーの"
                    "名前 (例: \"リン\")。同名衝突時は ``#N`` を含めて指定。"
                    "say / shout では指定しても無視される。"
                ),
            },
            "inner_thought": _IT,
        },
        "required": ["channel", "content", "inner_thought"],
    },
)


PREPARE_ACTION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    description="協力アクションの準備をする。他のプレイヤーが対応するアクションを実行できるようになる。例えば、ドアを支える準備をすることで他のプレイヤーがそのドアを通れるようになる。",
    parameters={
        "type": "object",
        "properties": {
            "action_name": {
                "type": "string",
                "description": (
                    "準備する操作の名前。"
                    "『現在の状況』の対象行にある「使える操作」から、"
                    "``\"\"`` で囲まれた値をそのまま 1 つ選んで渡す。"
                    "表示名へ言い換えたり、表示に無い名前を推測したりしないこと。"
                ),
            },
            "inner_thought": _IT,
        },
        "required": ["action_name", "inner_thought"],
    },
)


USE_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    description=(
        "所持アイテムを使用する（消耗品のみ）。例: パンを食べて空腹を回復、"
        "ポーションを飲んでHP回復。"
        "これは自分が食べる・飲む行為で、相手には渡らない。"
        "同じ場所の相手に渡すには give_item を使う。"
        "アイテムを使いながら同 spot の他者へ短く声をかけたい場合は"
        " say_inline に一言を書ける (例: 「これで少しは持つ」)。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "使用するアイテムの名前 (例: 生の魚)。"
                    "『現在の状況』の「所持アイテム」には "
                    "``- \"生の魚\" x2 (食料) (腐敗)`` のように、渡すべき"
                    "item 名のみが ``\"\"`` で囲まれて表示される。"
                    "**``\"\"`` 内の値をそのまま渡すこと** (quote 記号は剥がして"
                    "中身だけ、または quote ごとどちらでも resolver が解釈する)。"
                    "数量 (xN) / 種別タグ / (腐敗) などの装飾は付けない。"
                    "同名で複数エントリある場合 (例: 新鮮/腐敗別の魚) は"
                    "``#N`` ordinal を含めて指定。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "inner_thought"],
    },
)


LISTEN_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_LISTEN,
    description=(
        "耳を澄まして周囲の『環境音』を観測する。今いるスポットと、隣接する"
        "スポット (1ホップ分減衰) で発生している環境音 (扉のきしみ、水音、"
        "風、機械音など) を一覧として受け取る。\n"
        "重要な制約:\n"
        "- 他プレイヤーの発話 (speak の声) はこのツールでは聞こえない。"
        "発話は発火と同時に聴覚範囲内の listener へ自動配信されるため、"
        "後追いでこのツールを使っても過去の声を聞き直すことはできない\n"
        "- 「相手の声が聞こえないか確認したい」「聞き取れなかった声を聞き取り"
        "直したい」目的では使わない。それらは別の場所へ移動するか、相手に"
        "声を返してもらう以外に手段がない\n"
        "- 何も観測されないときは「何も聞こえなかった」が返る"
    ),
    parameters={
        "type": "object",
        "properties": {
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)


DROP_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    description=(
        "所持アイテムを現在地の地面に置く。同じスポットに居る他プレイヤーが"
        "後で pickup_item で拾える。協力のために素材を渡したい時、または"
        "持ち物を整理したい時に使う。地面に置いたアイテムはスポットを離れても消えず、"
        "誰かが拾うまで残る (シナリオで明示的に消去されない限り)。\n"
        "stealth=true にすると同じスポットに居る他者にも観測されず、こっそり"
        "アイテムを置ける (隠匿行為)。誰かに見られたくない時に使う。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "落とすアイテムの名前 (例: 流木)。"
                    "『現在の状況』の「所持アイテム」で ``\"\"`` で囲まれて"
                    "表示された値をそのまま渡す (装飾サフィックスは付けない)。"
                    "同じ種類のアイテムを複数所持している場合 (例: 流木 x2) は、"
                    "そのうち 1 つだけが落とされる。同じ名前が複数あるときは"
                    "``#N`` を含めて指定。"
                ),
            },
            "stealth": {
                "type": "boolean",
                "description": (
                    "true にすると同室他プレイヤーに観測されず、自分だけに記録される。"
                    "false なら従来通り「Xが流木を地面に置いた」が同室者に観測される。"
                ),
                "default": False,
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "inner_thought"],
    },
)


# PR-α (Y_after_pr639_640 後続): give_item を batch-always に統合し、
# 旧 give_items (別 tool) は削除。単発でも複数でも同じ tool で表現できるため
# LLM の認知負荷が減り、「give 系が 2 つある」混乱も解消する。
# 1 件だけ渡したいときは gives 配列の length を 1 にする (union 型は避けた)。
GIVE_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    description=(
        "同じスポットに居る別のプレイヤーへ所持アイテムを直接渡す。"
        "素材の受け渡しだけでなく、飢えた相手へ食料を分ける、"
        "負傷した相手へ回復アイテムを渡す手段でもある。"
        "**1 tick で複数のペア (アイテム × 相手) をまとめて処理できる** "
        "(単発でも複数配布でも同じ tool を使う)。1 つだけ渡したいときも "
        "``gives`` 配列の要素数を 1 にして渡す "
        "(単発でも配列で渡すルールを崩さない)。"
        "地面を経由せずに直接渡せるが、その場の第三者に「Xが流木をYに渡した」と観測される。"
        "受取り側のインベントリが満杯だと受け取れない (相手の手が空くのを待つか、"
        "別の相手を指定する)。**部分成功**: 1 件失敗しても他の "
        "項目は独立に実行され、結果メッセージに OK / NG がまとめて返る。"
        "受け渡しながら報告・段取り・呼びかけをしたい場合は say_inline を書ける "
        "(全ての受け渡しが終わったあとに 1 度だけ発火)。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "gives": {
                "type": "array",
                "description": (
                    "渡すアイテム × 相手のペア配列。1 件でも複数件でも "
                    "同じ形で渡す。順序どおりに処理される。"
                ),
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "item_label": {
                            "type": "string",
                            "description": (
                                "渡すアイテムの名前 (例: 流木)。"
                                "「所持アイテム」で ``\"\"`` で囲まれた値を"
                                "そのまま渡す。同じ名前が複数あるときは "
                                "``#N`` を含めて指定。"
                            ),
                        },
                        "target_player_label": {
                            "type": "string",
                            "description": (
                                "渡す相手の名前 (例: トマ)。"
                                "同名衝突時は ``#N`` を含めて指定。"
                                "自分自身は指定不可。"
                            ),
                        },
                        "quantity": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "同じ品を渡す個数 (省略時は 1)。"
                                "手元にある数より多く指定した場合は"
                                "**渡せるだけ渡し、渡した数を結果に返す**。"
                            ),
                        },
                    },
                    "required": ["item_label", "target_player_label"],
                },
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["gives", "inner_thought"],
    },
)


PICKUP_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    description=(
        "現在地の地面に落ちているアイテムを拾い上げて自分のインベントリに加える。"
        "他プレイヤーが地面に置いた素材を受け取ったり、シナリオで初期配置された"
        "アイテムを取得する。インベントリが満杯だと拾えない。\n"
        "stealth=true にすると同じスポットに居る他者にも観測されず、こっそり"
        "アイテムを拾える (盗み)。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "ground_item_label": {
                "type": "string",
                "description": (
                    "拾うアイテムの名前 (例: 流木)。『現在の状況』の「地面に"
                    "落ちているもの」では ``- \"流木\"`` のように item 名が"
                    "``\"\"`` で囲まれて表示される。**``\"\"`` 内の値をそのまま"
                    "渡すこと**。同じ名前が複数あるときは ``#N`` を含めて指定。"
                ),
            },
            "stealth": {
                "type": "boolean",
                "description": (
                    "true にすると同室他プレイヤーに観測されず、自分だけに記録される。"
                    "false なら従来通り「Xが流木を拾い上げた」"
                    "が同室者に観測される。"
                ),
                "default": False,
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["ground_item_label", "inner_thought"],
    },
)


ATTACK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_ATTACK,
    description=(
        "同じスポットに居るモンスターを攻撃する。"
        "**素手のダメージは小さく、装備している武器があればそれで威力が変わる。**"
        "相手の HP は正確な数値では見えず、モンスター section の "
        "``（〜・健康）`` / ``（〜・弱っている）`` / ``（〜・瀕死）`` の "
        "3 段階だけ観測できる。「健康」の相手を素手で倒すのは危険で、"
        "反対に「瀕死」なら止めを刺せる可能性がある。"
        "攻撃は 1 tick で 1 発 (相手も反撃してくる)。連続被弾で HP を"
        "失うより、``travel_to`` で別の spot へ **逃走** する方が"
        "安全なこともあり、状況で選ぶこと。"
        "戦闘中に同 spot の仲間へ短く声をかけたい場合は say_inline に"
        "一言を書ける (例: 「離れろ！」「援護頼む」)。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_label": {
                "type": "string",
                "description": (
                    "攻撃対象モンスターの名前 (例: \"灰色のオオカミ\")。"
                    "同種が複数いる場合は ``#N`` ordinal を含めて指定"
                    "(例: \"灰色のオオカミ #2\")。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["target_label", "inner_thought"],
    },
)


TEND_TO_PLAYER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    description=(
        "同じ場所でダウン状態 (HP 0 で倒れている) の仲間を蘇生させる。"
        "アイテム (救急用品) を持っていなくても、物理的に揺さぶり起こす形で"
        "蘇生でき、HP は最大値の 60% で復帰する。"
        "前提: 対象が同じ場所にいて、HP 0 でダウン状態であること。"
        "**疲労や空腹が高いだけ (= まだ立って動ける状態) の相手には使えない。**"
        "「顔色が悪い」「疲れて見える」「介抱したい」と感じても、HP 0 でない限り"
        "この tool は失敗する。"
        "そうした相手にはまず ``speak`` で話しかけるか食料を与えること。"
        "自分自身を蘇生することはできない。"
        "介抱しながら短く声をかけたい場合は say_inline に一言を書ける "
        "(例: 「大丈夫か！」「起きろ！」)。同 spot の第三者にも介抱している"
        "様子が SAY として届くので、他プレイヤーが状況を把握できる。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_player_label": {
                "type": "string",
                "description": (
                    "介抱する相手の名前 (例: \"エイダ\")。同名衝突時は"
                    "``#N`` ordinal を含めて指定。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": inner_thought_property(),
        },
        "required": ["target_player_label", "inner_thought"],
    },
)


VOTE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_VOTE,
    description=(
        "話し合いの場で、追放する相手に 1 票を投じる。**会議中だけ使える。**"
        "最も多く票を集めた 1 人が追放される。同数で並んだ場合は誰も追放され"
        "ない。"
        "確信が持てないときは target_player_label を空にして棄権できる。"
        "**棄権も 1 票として数える。** 棄権が最多なら誰も追放されない。"
        "情報が足りないのに誰かを名指しするより、保留するほうが良いことも"
        "ある。"
        "一度投じたら変えられない。全員が投じ終えた時点で集計され、結果は"
        "誰が誰に入れたかまで全員に伝わる。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_player_label": {
                "type": "string",
                "description": (
                    "追放したい相手の名前 (例: \"エイダ\")。"
                    "棄権する場合は空文字にする。"
                ),
            },
            "inner_thought": inner_thought_property(),
        },
        "required": ["inner_thought"],
    },
)


REPORT_BODY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    description=(
        "同じ場所で倒れている相手を見つけたと、その場の全員に知らせる。"
        "**自由時間だけ使える。**"
        "知らせると全員がここへ集まり、話し合いが始まる。"
        "集まる先はあなたが今いる場所なので、倒れている相手のそばで"
        "話し合うことになる。"
        "呼べるのは倒れている相手が同じ場所にいるときだけで、同じ相手に"
        "ついて二度は呼べない。緊急招集と違って回数の制限は無い。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_player_label": {
                "type": "string",
                "description": "倒れている相手の名前 (例: \"アオイ\")。",
            },
            "inner_thought": inner_thought_property(),
        },
        "required": ["target_player_label", "inner_thought"],
    },
)


#: 売買の共通注意書き。買いと売りで同じ約束をするので 1 か所に置く。
_TRADE_COMMON = (
    "商人と同じ場所に居るときだけ使える (別の場所からは取引できない)。"
    "取引はその場の第三者に観測される。"
    "品名と価格は『現在の状況』の「商人:」に出ているものを、"
    "``\"\"`` の中身そのままで指定する。"
    "**give_item と違って部分成功しない**: 数量ぶんすべて成立するか、"
    "1 つも成立せずに失敗するかのどちらかになる。"
)


BUY_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    description=(
        "同じ場所に居る商人から品を買う。所持金が代金ぶん減り、買った品が"
        "持ち物に入る。" + _TRADE_COMMON +
        "所持金が足りない / 持ち物に空きが無いときは何も買わずに失敗する。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "買う品の名前 (例: パン)。「商人:」の売りの行で "
                    "``\"\"`` に囲まれている値をそのまま渡す。"
                ),
            },
            "quantity": {
                "type": "integer",
                "description": "買う個数。1 以上 99 以下。",
                "minimum": 1,
                "maximum": 99,
            },
            "merchant_label": {
                "type": "string",
                "description": (
                    "商人の名前 (例: 商人グスタフ)。**同じ品を複数の商人が"
                    "扱っているときだけ指定する。** 省略すれば、その品を扱う"
                    "商人が 1 人ならその商人と取引する。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "inner_thought"],
    },
)


SELL_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    description=(
        "同じ場所に居る商人へ持ち物を売る。売った品が持ち物から消え、"
        "買値ぶん所持金が増える。" + _TRADE_COMMON +
        "その商人が買い取らない品や、持っている数より多い個数は売れない。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "売る品の名前 (例: 薬草)。「所持アイテム」に出ている名前を"
                    "そのまま渡す。買い取り価格は「商人:」の買いの行に出る。"
                ),
            },
            "quantity": {
                "type": "integer",
                "description": "売る個数。1 以上 99 以下。",
                "minimum": 1,
                "maximum": 99,
            },
            "merchant_label": {
                "type": "string",
                "description": (
                    "商人の名前 (例: 商人グスタフ)。**同じ品を複数の商人が"
                    "買い取るときだけ指定する。**"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "inner_thought"],
    },
)


#: 取引の片側を書く形。gives と asks で同じ形を使う。
#: 差し出す側と求める側で**共通のきまり**。両側に書くと同じ文が 2 度出る。
#:
#: 個々の項目ではなく、ツールの説明に 1 度だけ置く。schema は LLM が読む形なので、
#: **同じことを 2 か所に書くと、長くなるだけで意味は増えない。**
_TRADE_RULES = (
    "**gold は gives と asks のどちらか片側にだけ**置ける (金だけの両替はできない)。"
    "品の名前は「所持アイテム」に出ている表記をそのまま書く。"
    "**相手の持ち物は見えない**ので、求める品も名前で指名する。"
)


def _trade_side_schema(role: str) -> dict:
    """差し出す側 / 求める側の中身。**きまりは親側に 1 度だけ書く。**"""
    return {
        "type": "object",
        "description": f"{role}。品と gold のどちらか、または両方を書ける。",
        "properties": {
            "items": {
                "type": "array",
                "description": "品の並び。空でもよい (gold だけを出す場合)。",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_label": {
                            "type": "string",
                            "description": "品の名前 (例: パン)。",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "個数。1 以上。",
                            "minimum": 1,
                        },
                    },
                    "required": ["item_label", "quantity"],
                },
            },
            "gold": {
                "type": "integer",
                "description": "金額。0 なら書かなくてよい。",
                "minimum": 0,
            },
        },
    }


TRADE_OFFER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    description=(
        "同じ場所に居る相手へ、交換を持ちかける。"
        "**差し出すものは返事があるまで手元で凍結され、使ったり売ったりできなくなる** "
        "(相手が受けたときに確実に渡すため)。"
        "相手の手番で受けるか断るかが決まり、返事が無いまま時間が経つと流れる。"
        "持ちかけたことと中身は、その場の第三者にも見える。"
        "相手が持っていない品を求めてもよい (断られるだけ)。"
        "**部分的には成立しない**: 書いた組み合わせがそのまま成立するか、"
        "成立しないかのどちらか。"
        + _TRADE_RULES
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_player_label": {
                "type": "string",
                "description": (
                    "持ちかける相手の名前 (例: トマ)。同名衝突時は ``#N`` を含めて指定。"
                    "自分自身は指定不可。"
                ),
            },
            "gives": _trade_side_schema("自分が差し出すもの"),
            "asks": _trade_side_schema("相手に求めるもの"),
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["target_player_label", "gives", "asks", "inner_thought"],
    },
)


TRADE_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    description=(
        "自分に持ちかけられている取引を受ける。"
        "その場で品と金が入れ替わる。求められたものを持っていないと成立せず、"
        "その場合は提案が残るので、集めてから受け直せる。"
        "成立したことは、その場の第三者にも見える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "offerer_player_label": {
                "type": "string",
                "description": (
                    "誰の申し出を受けるか (例: レナ)。"
                    "**自分宛ての申し出が 1 件だけなら省略できる。**"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)


TRADE_DECLINE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    description=(
        "自分に持ちかけられている取引を断る。"
        "断ると相手の凍結が解け、相手はその品をまた使えるようになる。"
        "返事をせずに放っておくこともできるが、その場合は時間切れまで"
        "相手の品が凍結されたままになる。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "offerer_player_label": {
                "type": "string",
                "description": (
                    "誰の申し出を断るか (例: レナ)。"
                    "**自分宛ての申し出が 1 件だけなら省略できる。**"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)


# ── 市場の掲示板 (経済統合 Phase 3) ──────────────────────────────────
#
# 板は物理的に置かれた物なので、同席していないと使えない (離れていても
# ツールは出る。実行時に MARKET_BOARD_NOT_HERE で断る)。
#
# 買う側は注文を選ばない。表示が「18G で買える (出品 3件)」と集約されて
# いるので、どの注文を指すかを表示から組み立てられない。品と数だけを
# 指定し、安い方から順に買う。
#
# 自分の注文は「同じ品目・同じ向きで 1 件まで」に制限されているので、
# 品名と向きで一意に指せる。

MARKET_LIST_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    description=(
        "市場の掲示板に品を出品する。**出した品は板に預けられ、手元から無くなる** "
        "(売れるか、取り下げるか、期限切れで戻るまで使えない)。"
        "値は 1 つあたりの単価で書く。"
        "同じ品の出品は 1 件までで、値を変えたいときは market_reprice を使う。"
        "板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "出す品の名前 (例: 焼きたてのパン)。所持品に出ている名前をそのまま書く。",
            },
            "quantity": {"type": "integer", "description": "出す個数 (1 以上)。"},
            "unit_price": {
                "type": "integer",
                "description": "1 つあたりの値段 (G、1 以上)。合計ではない。",
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "unit_price", "inner_thought"],
    },
)

MARKET_BUY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    description=(
        "市場の掲示板から品を買う。**安く出ているものから順に買う**ので、"
        "どの出品を買うかは指定しない。"
        "出ている数が足りなければ、出ている分だけ買う。"
        "所持金が足りないときは 1 つも買わない。"
        "自分の出品は買えない (飛ばされる)。板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "買う品の名前 (例: 焼きたてのパン)。掲示板に出ている名前をそのまま書く。",
            },
            "quantity": {"type": "integer", "description": "買いたい個数 (1 以上)。"},
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "inner_thought"],
    },
)

MARKET_REPRICE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    description=(
        "掲示板に出している自分の注文の値段を変える。"
        "**品は板に預けたままなので、手持ちがいっぱいでも使える**。"
        "残っている個数と期限は変わらない。板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "値を変える注文の品名。「あなたの出品」に出ている名前をそのまま書く。",
            },
            "side": {
                "type": "string",
                "enum": ["sell"],
                "description": "売り注文か買い注文か。いまは売り注文 (sell) だけ。",
            },
            "new_unit_price": {
                "type": "integer",
                "description": "新しい 1 つあたりの値段 (G、1 以上)。",
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "new_unit_price", "inner_thought"],
    },
)

MARKET_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    description=(
        "掲示板に出している自分の注文を取り下げ、預けた品を引き取る。"
        "**手持ちに空きが無いと引き取れない**ので、先に何か手放す必要がある。"
        "値を変えたいだけなら market_reprice の方が確実。"
        "板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "取り下げる注文の品名。「あなたの出品」に出ている名前をそのまま書く。",
            },
            "side": {
                "type": "string",
                "enum": ["sell"],
                "description": "売り注文か買い注文か。いまは売り注文 (sell) だけ。",
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "inner_thought"],
    },
)


MARKET_BID_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    description=(
        "市場の掲示板に買い注文を出す。「この品をこの値で買う」と掲げて、"
        "誰かが売りに来るのを待つ。"
        "**代金は板に預けられ、手元から無くなる** (売られるか、取り下げるか、"
        "期限切れで戻るまで使えない)。"
        "相手が同じ場所に居なくても取引が成り立つのが、掲示板の利点。"
        "同じ品の買い注文は 1 件までで、値を変えたいときは market_reprice を使う。"
        "板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "求める品の名前 (例: 麦束)。この世界にある品名をそのまま書く。",
            },
            "quantity": {"type": "integer", "description": "求める個数 (1 以上)。"},
            "unit_price": {
                "type": "integer",
                "description": "1 つあたりに払う値段 (G、1 以上)。合計ではない。",
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "unit_price", "inner_thought"],
    },
)

MARKET_SELL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    description=(
        "市場の掲示板に出ている買い注文へ売る。**高く買う注文から順に売れる**"
        "ので、どの注文へ売るかは指定しない。"
        "求められている数が足りなければ、その分だけ売る。"
        "持っている数が足りなければ、持っている分だけ売る。"
        "自分の買い注文へは売れない (飛ばされる)。板と同じ場所に居るときだけ使える。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": "売る品の名前。所持品に出ている名前をそのまま書く。",
            },
            "quantity": {"type": "integer", "description": "売りたい個数 (1 以上)。"},
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "quantity", "inner_thought"],
    },
)


def get_spot_graph_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (TRAVEL_TO_DEFINITION, _RESOLVER),
        (SET_SUB_LOCATION_DEFINITION, _RESOLVER),
        (EXPLORE_DEFINITION, _RESOLVER),
        (INTERACT_DEFINITION, _RESOLVER),
        (PREPARE_ACTION_DEFINITION, _RESOLVER),
        (USE_ITEM_DEFINITION, _RESOLVER),
        (DROP_ITEM_DEFINITION, _RESOLVER),
        (PICKUP_ITEM_DEFINITION, _RESOLVER),
        (GIVE_ITEM_DEFINITION, _RESOLVER),
        (BUY_ITEM_DEFINITION, _RESOLVER),
        (SELL_ITEM_DEFINITION, _RESOLVER),
        (TRADE_OFFER_DEFINITION, _RESOLVER),
        (TRADE_ACCEPT_DEFINITION, _RESOLVER),
        (TRADE_DECLINE_DEFINITION, _RESOLVER),
        (MARKET_LIST_ITEM_DEFINITION, _RESOLVER),
        (MARKET_BUY_DEFINITION, _RESOLVER),
        (MARKET_REPRICE_DEFINITION, _RESOLVER),
        (MARKET_CANCEL_DEFINITION, _RESOLVER),
        (MARKET_BID_DEFINITION, _RESOLVER),
        (MARKET_SELL_DEFINITION, _RESOLVER),
        (ATTACK_DEFINITION, _RESOLVER),
        (LISTEN_DEFINITION, _RESOLVER),
        (WAIT_DEFINITION, _RESOLVER),
        (TEND_TO_PLAYER_DEFINITION, _RESOLVER),
        (VOTE_DEFINITION, _RESOLVER),
        (REPORT_BODY_DEFINITION, _RESOLVER),
        (SPEECH_DEFINITION, _RESOLVER),
    ]


__all__ = [
    "get_spot_graph_specs",
    "TRAVEL_TO_DEFINITION",
    "SET_SUB_LOCATION_DEFINITION",
    "EXPLORE_DEFINITION",
    "INTERACT_DEFINITION",
    "PREPARE_ACTION_DEFINITION",
    "USE_ITEM_DEFINITION",
    "DROP_ITEM_DEFINITION",
    "PICKUP_ITEM_DEFINITION",
    "GIVE_ITEM_DEFINITION",
    "BUY_ITEM_DEFINITION",
    "SELL_ITEM_DEFINITION",
    "TRADE_OFFER_DEFINITION",
    "TRADE_ACCEPT_DEFINITION",
    "TRADE_DECLINE_DEFINITION",
    "MARKET_LIST_ITEM_DEFINITION",
    "MARKET_BUY_DEFINITION",
    "MARKET_REPRICE_DEFINITION",
    "MARKET_CANCEL_DEFINITION",
    "MARKET_BID_DEFINITION",
    "MARKET_SELL_DEFINITION",
    "ATTACK_DEFINITION",
    "LISTEN_DEFINITION",
    "WAIT_DEFINITION",
    "TEND_TO_PLAYER_DEFINITION",
    "VOTE_DEFINITION",
    "REPORT_BODY_DEFINITION",
    "SPEECH_DEFINITION",
    "SPEECH_CHANNEL_WHISPER",
    "SPEECH_CHANNEL_SAY",
    "SPEECH_CHANNEL_SHOUT",
    "SPEECH_CHANNEL_VALUES",
]
