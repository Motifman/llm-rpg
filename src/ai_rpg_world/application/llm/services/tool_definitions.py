"""LLM ツールの定義（名前・説明・parameters スキーマ）とデフォルト登録"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IGameToolRegistry
from ai_rpg_world.application.llm.services.availability_resolvers import (
    ChangeAttentionAvailabilityResolver,
    ChestStoreAvailabilityResolver,
    ChestTakeAvailabilityResolver,
    CombatUseSkillAvailabilityResolver,
    ConversationAdvanceAvailabilityResolver,
    DestroyPlaceableAvailabilityResolver,
    HarvestStartAvailabilityResolver,
    InteractAvailabilityResolver,
    NoOpAvailabilityResolver,
    PlaceObjectAvailabilityResolver,
    SayAvailabilityResolver,
    SetDestinationAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)

# no_op: パラメータなし
NO_OP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_NO_OP,
    description="何もしない。このターンは行動を起こさず待機します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

# 移動（1 ツール）。内部では destination_label を runtime context で既存の destination args に解決する。
MOVE_TO_DESTINATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "destination_label": {
            "type": "string",
            "description": "現在の状況に表示された移動先ラベル（例: S1）。",
        },
    },
    "required": ["destination_label"],
}

MOVE_TO_DESTINATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MOVE_TO_DESTINATION,
    description="指定した目的地（スポットまたはロケーション）へ移動します。",
    parameters=MOVE_TO_DESTINATION_PARAMETERS,
)

WHISPER_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示されたプレイヤーラベル（例: P1）。",
        },
        "content": {
            "type": "string",
            "description": "囁く内容。",
        },
    },
    "required": ["target_label", "content"],
}

WHISPER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_WHISPER,
    description="視界内の特定プレイヤーにだけ囁きを送ります。",
    parameters=WHISPER_PARAMETERS,
)

SAY_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "周囲に向けて発言する内容。",
        },
    },
    "required": ["content"],
}

SAY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SAY,
    description="周囲に聞こえるように発言します。",
    parameters=SAY_PARAMETERS,
)

INTERACT_WORLD_OBJECT_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示された相互作用対象ラベル（例: N1, O1）。",
        },
    },
    "required": ["target_label"],
}

INTERACT_WORLD_OBJECT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_INTERACT_WORLD_OBJECT,
    description="視界内の対象に話しかける、開ける、調べるなどの相互作用を行います。",
    parameters=INTERACT_WORLD_OBJECT_PARAMETERS,
)

HARVEST_START_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示された採集対象ラベル（例: O1）。",
        },
    },
    "required": ["target_label"],
}

HARVEST_START_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_HARVEST_START,
    description="視界内の資源に対して採集を開始します。",
    parameters=HARVEST_START_PARAMETERS,
)

CHANGE_ATTENTION_PARAMETERS = {
    "type": "object",
    "properties": {
        "level_label": {
            "type": "string",
            "description": "現在の状況に表示された注意レベルラベル（例: A1）。",
        },
    },
    "required": ["level_label"],
}

CHANGE_ATTENTION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CHANGE_ATTENTION,
    description="注意レベルを変更して、次のターン以降に受け取る観測の粒度を切り替えます。",
    parameters=CHANGE_ATTENTION_PARAMETERS,
)

CONVERSATION_ADVANCE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "会話相手のラベル（例: N1）。",
        },
        "choice_label": {
            "type": "string",
            "description": "現在の会話に表示された選択肢ラベル（例: R1）。「次へ」の場合は省略可。",
        },
    },
    "required": ["target_label"],
}

CONVERSATION_ADVANCE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CONVERSATION_ADVANCE,
    description="現在進行中の会話を次へ進めるか、選択肢を選びます。",
    parameters=CONVERSATION_ADVANCE_PARAMETERS,
)

PLACE_OBJECT_PARAMETERS = {
    "type": "object",
    "properties": {
        "inventory_item_label": {
            "type": "string",
            "description": "現在の状況に表示された在庫アイテムラベル（例: I1）。",
        },
    },
    "required": ["inventory_item_label"],
}

PLACE_OBJECT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_PLACE_OBJECT,
    description="設置可能な在庫アイテムをプレイヤー前方に設置します。",
    parameters=PLACE_OBJECT_PARAMETERS,
)

DESTROY_PLACEABLE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_DESTROY_PLACEABLE,
    description="プレイヤー前方の設置物を破壊して回収します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

CHEST_STORE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "対象の宝箱ラベル（例: O1）。",
        },
        "inventory_item_label": {
            "type": "string",
            "description": "収納する在庫アイテムラベル（例: I1）。",
        },
    },
    "required": ["target_label", "inventory_item_label"],
}

CHEST_STORE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CHEST_STORE,
    description="開いている宝箱に在庫アイテムを収納します。",
    parameters=CHEST_STORE_PARAMETERS,
)

CHEST_TAKE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "対象の宝箱ラベル（例: O1）。",
        },
        "chest_item_label": {
            "type": "string",
            "description": "宝箱の中身ラベル（例: C1）。",
        },
    },
    "required": ["target_label", "chest_item_label"],
}

CHEST_TAKE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CHEST_TAKE,
    description="開いている宝箱からアイテムを取り出します。",
    parameters=CHEST_TAKE_PARAMETERS,
)

COMBAT_USE_SKILL_PARAMETERS = {
    "type": "object",
    "properties": {
        "skill_label": {
            "type": "string",
            "description": "現在の状況に表示された使用可能スキルラベル（例: K1）。",
        },
        "target_label": {
            "type": "string",
            "description": "攻撃対象ラベル（例: M1, P1）。省略時は自動照準または現在向きを使います。",
        },
    },
    "required": ["skill_label"],
}

COMBAT_USE_SKILL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_COMBAT_USE_SKILL,
    description="使用可能スキルを選んで発動します。対象があればその方向へ向き直ります。",
    parameters=COMBAT_USE_SKILL_PARAMETERS,
)


def register_default_tools(
    registry: IGameToolRegistry,
    *,
    speech_enabled: bool = False,
    interaction_enabled: bool = False,
    harvest_enabled: bool = False,
    attention_enabled: bool = False,
    conversation_enabled: bool = False,
    place_enabled: bool = False,
    chest_enabled: bool = False,
    combat_enabled: bool = False,
) -> None:
    """標準ツール群を登録し、依存サービスがあるカテゴリだけ追加する。"""
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")
    registry.register(NO_OP_DEFINITION, NoOpAvailabilityResolver())
    registry.register(MOVE_TO_DESTINATION_DEFINITION, SetDestinationAvailabilityResolver())
    if speech_enabled:
        registry.register(WHISPER_DEFINITION, WhisperAvailabilityResolver())
        registry.register(SAY_DEFINITION, SayAvailabilityResolver())
    if interaction_enabled:
        registry.register(INTERACT_WORLD_OBJECT_DEFINITION, InteractAvailabilityResolver())
    if harvest_enabled:
        registry.register(HARVEST_START_DEFINITION, HarvestStartAvailabilityResolver())
    if attention_enabled:
        registry.register(CHANGE_ATTENTION_DEFINITION, ChangeAttentionAvailabilityResolver())
    if conversation_enabled:
        registry.register(CONVERSATION_ADVANCE_DEFINITION, ConversationAdvanceAvailabilityResolver())
    if place_enabled:
        registry.register(PLACE_OBJECT_DEFINITION, PlaceObjectAvailabilityResolver())
        registry.register(DESTROY_PLACEABLE_DEFINITION, DestroyPlaceableAvailabilityResolver())
    if chest_enabled:
        registry.register(CHEST_STORE_DEFINITION, ChestStoreAvailabilityResolver())
        registry.register(CHEST_TAKE_DEFINITION, ChestTakeAvailabilityResolver())
    if combat_enabled:
        registry.register(COMBAT_USE_SKILL_DEFINITION, CombatUseSkillAvailabilityResolver())
