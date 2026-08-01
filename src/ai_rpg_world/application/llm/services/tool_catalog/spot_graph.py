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
                    "対象の名前 (例: 焚き火跡)。"
                    "『現在の状況』のオブジェクト section では "
                    "``- \"焚き火跡\" (available=true) — 説明 [gather, examine]`` "
                    "のように、渡すべき object 名のみが ``\"\"`` で囲まれて表示される。"
                    "**``\"\"`` 内の値をそのまま渡すこと** (quote 記号は剥がして"
                    "中身だけ、または quote ごとどちらでも resolver が解釈する)。"
                    "同名衝突時は ``#N`` ordinal を含めて指定。"
                ),
            },
            "action_name": {
                "type": "string",
                "description": (
                    "オブジェクトに定義された action_name "
                    "(例: gather / search / examine)。"
                    "『現在の状況』のオブジェクト行末尾 ``[gather, examine]`` "
                    "のカンマ区切り配列から、そのまま 1 つを選んで渡す。"
                    "日本語や敬体ではなく、英語の動詞形を渡す。"
                    "思いつきで推測せず、必ず表示された値のいずれかを使うこと。"
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
        "drop→pickup の手間を省くが、その場の第三者に「Xが流木をYに渡した」と観測される。"
        "受取り側のインベントリが満杯だと受け取れない (相手が drop するのを待つか、"
        "別の相手を指定する)。**部分成功**: 1 件失敗しても他の "
        "項目は独立に実行され、結果メッセージに OK / NG がまとめて返る。"
        "受け渡しながら報告・段取り・呼びかけをしたい場合は say_inline を書ける "
        "(全 give 完了後に 1 度だけ発火)。"
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
