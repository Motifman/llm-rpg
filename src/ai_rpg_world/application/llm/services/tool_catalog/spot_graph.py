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
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
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

TRAVEL_TO_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    description="スポットグラフ上で、指定した接続先ラベルへ移動を開始する（経路は最短・通行条件を満たす必要がある）。",
    parameters={
        "type": "object",
        "properties": {
            "destination_label": {
                "type": "string",
                "description": (
                    "接続先ラベル（現在の状況に表示された S1, S2 等）または"
                    "スポット名そのもの（例: \"入口広間\"）。"
                    "スポット名は意味が不変なので、過去 turn の履歴を参照して"
                    "再利用する場合はスポット名の方が安全。\n"
                    "現在状況の \"S2: 扉 → 館長書斎\" のような行をそのまま"
                    "貼っても解決を試みるが、可能なら S2 または \"館長書斎\" "
                    "のみを渡す方が確実。"
                ),
            },
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
                    "サブロケーションラベル（現在の状況に表示された SL1, SL2 等）"
                    "またはサブロケーション名そのもの（例: \"祭壇前\"）。未指定でクリア。"
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
    description="現在のスポット内のオブジェクトに対し、指定した操作名で相互作用する。パズル操作の場合はparametersに入力値を指定する。",
    parameters={
        "type": "object",
        "properties": {
            "object_label": {
                "type": "string",
                "description": "オブジェクトラベル（現在の状況に表示された OBJ1, OBJ2 等）。",
            },
            "action_name": {
                "type": "string",
                "description": "操作名（オブジェクトに定義された action_name）。",
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
                    "channel=whisper のときのみ必須。同じ場所にいるプレイヤーラベル"
                    " (P1, P2 等) または相手の名前 (例: \"リン\")。"
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
                "description": "使用するアイテムラベル（所持アイテムに表示された I1, I2 等）。",
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
                    "落とすアイテムのラベル (所持アイテムに表示された I1, I2 等)。"
                    "同じ spec のアイテムを複数所持している場合 (例: I1: 流木 x2) は、"
                    "代表 instance が1つだけ落とされる。"
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
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_label": {
                "type": "string",
                "description": (
                    "渡すアイテムのラベル (所持アイテムに表示された I1, I2 等)。"
                    "同 spec で複数所持の場合は代表 instance が 1 つ渡される。"
                ),
            },
            "target_player_label": {
                "type": "string",
                "description": (
                    "渡す相手のラベル (同スポット内のプレイヤー一覧に表示された "
                    "P1, P2 等) または相手の名前 (例: \"トマ\")。自分自身は指定不可。"
                ),
            },
            "inner_thought": _IT,
        },
        "required": ["item_label", "target_player_label", "inner_thought"],
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
                    "拾うアイテムのラベル (現在の状況の「地面に落ちているもの」に"
                    "表示された G1, G2 等)。"
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
                "description": "攻撃対象のモンスターラベル（M1, M2 等）。",
            },
            "inner_thought": _IT,
        },
        "required": ["target_label", "inner_thought"],
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
        (ATTACK_DEFINITION, _RESOLVER),
        (LISTEN_DEFINITION, _RESOLVER),
        (WAIT_DEFINITION, _RESOLVER),
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
    "ATTACK_DEFINITION",
    "LISTEN_DEFINITION",
    "WAIT_DEFINITION",
    "SPEECH_DEFINITION",
    "SPEECH_CHANNEL_WHISPER",
    "SPEECH_CHANNEL_SAY",
    "SPEECH_CHANNEL_SHOUT",
    "SPEECH_CHANNEL_VALUES",
]
