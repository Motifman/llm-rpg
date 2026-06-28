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
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
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
# 実験 #29 後続: 移動 / アイテム系ツールで「立ち去り際 / 受け渡し際の一言」を
# 任意で発話できるようにする。同 spot の他プレイヤーにだけ届く SAY 相当。
from ai_rpg_world.application.llm.services.tool_catalog.say_inline import (
    say_inline_property,
)
_SAY = say_inline_property()

TRAVEL_TO_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    description=(
        "スポットグラフ上で、指定した接続先へ移動を開始する（経路は最短・通行条件を満たす必要がある）。"
        "立ち去り際に同 spot の他者へ短く声をかけたい場合は say_inline に一言を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "destination_label": {
                "type": "string",
                "description": (
                    "行き先スポットの名前 (例: \"入口広間\")。"
                    "現在の状況の \"- 扉 → 館長書斎\" のような行に出ている"
                    "spot 名をそのまま渡す。"
                    "同名スポットが複数ある場合 (まれ) は ``#1`` / ``#2`` の"
                    "ordinal を含めて指定する (例: \"小部屋 #2\")。"
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
    description="現在のスポットを探索する（発見・ドロップ等はシナリオ依存）。",
    parameters={
        "type": "object",
        "properties": {
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
        "パズル操作の場合は parameters に入力値を指定する。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "object_label": {
                "type": "string",
                "description": (
                    "オブジェクトの名前 (例: \"焚き火跡\")。"
                    "同名衝突時は ``#N`` ordinal を含めて指定。"
                ),
            },
            "action_name": {
                "type": "string",
                "description": (
                    "オブジェクトに定義された action_name "
                    "(例: \"gather\", \"search\", \"examine\")。"
                    "日本語や敬体ではなく、英語の動詞形を渡す。"
                    "思いつきで推測せず、必ず『現在の状況』section に表示された"
                    "値をそのまま渡すこと。"
                ),
            },
            "parameters": {
                "type": "object",
                "description": "パズル入力等の追加パラメータ（例: {\"code\": \"1234\"}）。パズルでない操作では省略可。",
            },
            "inner_thought": _IT,
        },
        "required": ["object_label", "action_name", "inner_thought"],
    },
)

WAIT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_WAIT,
    description="その場で短く待機し、時間経過に伴う環境変化や出来事を観測する。",
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "待機する理由（任意）。",
            },
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
        "- shout: 同じスポット + 隣接 + さらに 1 hop 先 (2 hop) まで届く (大声で叫ぶ)"
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
            "action_id": {
                "type": "string",
                "description": "準備するアクションID（操作対象に表示される協力アクション名）。",
            },
            "inner_thought": _IT,
        },
        "required": ["action_id", "inner_thought"],
    },
)


USE_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    description="所持アイテムを使用する（消耗品のみ）。例: パンを食べて空腹を回復、ポーションを飲んでHP回復。",
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "使用するアイテムの名前 (例: \"生の魚\")。"
                    "同名で複数エントリある場合 (例: 新鮮/腐敗別の魚) は"
                    "``#N`` ordinal を含めて指定。"
                ),
            },
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
        "- 他プレイヤーの発話 (speech_speak の声) はこのツールでは聞こえない。"
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
        "持ち物を整理したい時に使う。地面アイテムはスポットを離れても消えず、"
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
                    "落とすアイテムの名前 (例: \"流木\")。"
                    "同じ spec のアイテムを複数所持している場合 (例: 流木 x2) は、"
                    "代表 instance が 1 つだけ落とされる。同名衝突時は"
                    "``#N`` ordinal を含めて指定。"
                ),
            },
            "stealth": {
                "type": "boolean",
                "description": (
                    "true にすると同室他プレイヤーに観測されない (witness_policy="
                    "ACTOR_ONLY)。false (default) なら従来通り「Xが流木を地面に"
                    "置いた」が同室者に観測される。"
                ),
                "default": False,
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "inner_thought"],
    },
)


GIVE_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    description=(
        "同じスポットに居る別のプレイヤーへ所持アイテムを直接渡す。drop して "
        "pickup させる手間を省くが、その場に居る第三者にも「Xが流木をYに渡した」"
        "と観測される。受取り側のインベントリが満杯だと受け取れない。"
        "受け渡し際に一言かけたい場合は say_inline を書ける。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "渡すアイテムの名前 (例: \"流木\")。"
                    "同 spec で複数所持の場合は代表 instance が 1 つ渡される。"
                    "同名衝突時は ``#N`` ordinal を含めて指定。"
                ),
            },
            "target_player_label": {
                "type": "string",
                "description": (
                    "渡す相手の名前 (例: \"トマ\")。同名衝突時は ``#N`` "
                    "ordinal を含めて指定。自分自身は指定不可。"
                ),
            },
            "say_inline": _SAY,
            "inner_thought": _IT,
        },
        "required": ["item_label", "target_player_label", "inner_thought"],
    },
)


GIVE_ITEMS_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS,
    description=(
        "**複数の** give_item を同 tick にまとめて実行する。``gives`` 配列の各 "
        "entry は ``give_item`` 単発と同じセマンティクスで処理される。各 entry "
        "は **partial success**: 一部が失敗 (受け手満杯・自分自身指定など) しても、"
        "他は実行され、結果メッセージに「OK / NG とその理由」が集約される。\n"
        "「複数の仲間に物を配り終えて移動する」のような協調行動を 1 turn で"
        "片付けたいときに使う。1 件だけ渡したい場合は ``give_item`` を使うのが"
        "簡潔。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "gives": {
                "type": "array",
                "description": (
                    "渡すアイテム × 渡し先のペア配列。各 entry は item_label と "
                    "target_player_label を持つ。順序通りに処理される。"
                ),
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "item_label": {
                            "type": "string",
                            "description": (
                                "渡すアイテムの名前 (例: \"流木\")。同名衝突時は "
                                "``#N`` ordinal を含めて指定。"
                            ),
                        },
                        "target_player_label": {
                            "type": "string",
                            "description": (
                                "渡す相手の名前 (例: \"トマ\")。同名衝突時は "
                                "``#N`` ordinal を含めて指定。自分自身は指定不可。"
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
        "他プレイヤーが drop した素材を受け取ったり、シナリオで初期配置された"
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
                    "拾うアイテムの名前 (例: \"流木\")。現在の状況の「地面に"
                    "落ちているもの」に表示された名前をそのまま渡す。"
                    "同名衝突時は ``#N`` ordinal を含めて指定。"
                ),
            },
            "stealth": {
                "type": "boolean",
                "description": (
                    "true にすると同室他プレイヤーに観測されない (witness_policy="
                    "ACTOR_ONLY)。false (default) なら従来通り「Xが流木を拾い上げた」"
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
    description="同じスポットに居るモンスターを攻撃する。",
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
            "inner_thought": _IT,
        },
        "required": ["target_label", "inner_thought"],
    },
)


TEND_TO_PLAYER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    description=(
        "同じ場所に倒れている仲間を介抱して意識を取り戻させる。"
        "アイテム (救急用品) を持っていなくても、物理的に揺さぶり起こす形で"
        "蘇生できる。HP は ``max_hp`` の 40% で復帰する。"
        "前提: 介抱対象が同じ場所にいて、戦闘不能状態であること。"
        "自分自身を介抱することはできない。"
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
            "inner_thought": inner_thought_property(),
        },
        "required": ["target_player_label", "inner_thought"],
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
        (GIVE_ITEMS_DEFINITION, _RESOLVER),
        (ATTACK_DEFINITION, _RESOLVER),
        (LISTEN_DEFINITION, _RESOLVER),
        (WAIT_DEFINITION, _RESOLVER),
        (TEND_TO_PLAYER_DEFINITION, _RESOLVER),
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
    "GIVE_ITEMS_DEFINITION",
    "ATTACK_DEFINITION",
    "LISTEN_DEFINITION",
    "WAIT_DEFINITION",
    "TEND_TO_PLAYER_DEFINITION",
    "SPEECH_DEFINITION",
    "SPEECH_CHANNEL_WHISPER",
    "SPEECH_CHANNEL_SAY",
    "SPEECH_CHANNEL_SHOUT",
    "SPEECH_CHANNEL_VALUES",
]
