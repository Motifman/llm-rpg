"""ワールド系ツールの定義（interact, harvest, inspect, attention, conversation, place, drop, chest）。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    ChangeAttentionAvailabilityResolver,
    ChestStoreAvailabilityResolver,
    ChestTakeAvailabilityResolver,
    ConversationAdvanceAvailabilityResolver,
    DestroyPlaceableAvailabilityResolver,
    DropItemAvailabilityResolver,
    HarvestCancelAvailabilityResolver,
    HarvestStartAvailabilityResolver,
    InspectItemAvailabilityResolver,
    InspectTargetAvailabilityResolver,
    InteractAvailabilityResolver,
    PlaceObjectAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_PLACE_OBJECT,
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

HARVEST_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "進行中の採集対象ラベル（例: H1）。",
        },
    },
    "required": ["target_label"],
}

HARVEST_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_HARVEST_CANCEL,
    description="進行中の採集を中断します。",
    parameters=HARVEST_CANCEL_PARAMETERS,
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

DROP_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "inventory_item_label": {
            "type": "string",
            "description": "現在の状況に表示された在庫アイテムラベル（例: I1）。捨てるアイテムを指定します。",
        },
    },
    "required": ["inventory_item_label"],
}

DROP_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_DROP_ITEM,
    description="在庫アイテムを地面に捨てます。",
    parameters=DROP_ITEM_PARAMETERS,
)

INSPECT_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "inventory_item_label": {
            "type": "string",
            "description": "現在の状況に表示された在庫アイテムラベル（例: I1）。",
        },
    },
    "required": ["inventory_item_label"],
}

INSPECT_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_INSPECT_ITEM,
    description="在庫アイテムの詳細説明を取得します。",
    parameters=INSPECT_ITEM_PARAMETERS,
)

INSPECT_TARGET_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示された対象ラベル（例: M1, O1, N1）。",
        },
    },
    "required": ["target_label"],
}

INSPECT_TARGET_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_INSPECT_TARGET,
    description="視界内の対象（モンスター、オブジェクト等）の詳細説明を取得します。",
    parameters=INSPECT_TARGET_PARAMETERS,
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


def _get_interaction_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(INTERACT_WORLD_OBJECT_DEFINITION, InteractAvailabilityResolver())]


def _get_harvest_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (HARVEST_START_DEFINITION, HarvestStartAvailabilityResolver()),
        (HARVEST_CANCEL_DEFINITION, HarvestCancelAvailabilityResolver()),
    ]


def _get_inspect_item_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(INSPECT_ITEM_DEFINITION, InspectItemAvailabilityResolver())]


def _get_inspect_target_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(INSPECT_TARGET_DEFINITION, InspectTargetAvailabilityResolver())]


def _get_attention_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(CHANGE_ATTENTION_DEFINITION, ChangeAttentionAvailabilityResolver())]


def _get_conversation_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(CONVERSATION_ADVANCE_DEFINITION, ConversationAdvanceAvailabilityResolver())]


def _get_place_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (PLACE_OBJECT_DEFINITION, PlaceObjectAvailabilityResolver()),
        (DESTROY_PLACEABLE_DEFINITION, DestroyPlaceableAvailabilityResolver()),
    ]


def _get_drop_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [(DROP_ITEM_DEFINITION, DropItemAvailabilityResolver())]


def _get_chest_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (CHEST_STORE_DEFINITION, ChestStoreAvailabilityResolver()),
        (CHEST_TAKE_DEFINITION, ChestTakeAvailabilityResolver()),
    ]


def get_world_specs(
    *,
    interaction_enabled: bool = False,
    harvest_enabled: bool = False,
    inspect_item_enabled: bool = False,
    inspect_target_enabled: bool = False,
    attention_enabled: bool = False,
    conversation_enabled: bool = False,
    place_enabled: bool = False,
    drop_enabled: bool = False,
    chest_enabled: bool = False,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """ワールド系ツールの (definition, resolver) 一覧を返す。有効なカテゴリのみ含む。"""
    specs: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if interaction_enabled:
        specs.extend(_get_interaction_specs())
    if harvest_enabled:
        specs.extend(_get_harvest_specs())
    if inspect_item_enabled:
        specs.extend(_get_inspect_item_specs())
    if inspect_target_enabled:
        specs.extend(_get_inspect_target_specs())
    if attention_enabled:
        specs.extend(_get_attention_specs())
    if conversation_enabled:
        specs.extend(_get_conversation_specs())
    if place_enabled:
        specs.extend(_get_place_specs())
    if drop_enabled:
        specs.extend(_get_drop_specs())
    if chest_enabled:
        specs.extend(_get_chest_specs())
    return specs


__all__ = [
    "get_world_specs",
    "CHANGE_ATTENTION_DEFINITION",
    "CHEST_STORE_DEFINITION",
    "CHEST_TAKE_DEFINITION",
    "CONVERSATION_ADVANCE_DEFINITION",
    "DESTROY_PLACEABLE_DEFINITION",
    "DROP_ITEM_DEFINITION",
    "HARVEST_CANCEL_DEFINITION",
    "HARVEST_START_DEFINITION",
    "INSPECT_ITEM_DEFINITION",
    "INSPECT_TARGET_DEFINITION",
    "INTERACT_WORLD_OBJECT_DEFINITION",
    "PLACE_OBJECT_DEFINITION",
]
