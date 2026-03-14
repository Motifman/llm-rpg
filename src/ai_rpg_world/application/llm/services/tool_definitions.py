"""LLM ツールの定義（名前・説明・parameters スキーマ）とデフォルト登録"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IGameToolRegistry
from ai_rpg_world.application.llm.services.availability_resolvers import (
    CancelMovementAvailabilityResolver,
    ChangeAttentionAvailabilityResolver,
    MoveOneStepAvailabilityResolver,
    ChestStoreAvailabilityResolver,
    ChestTakeAvailabilityResolver,
    CombatUseSkillAvailabilityResolver,
    ConversationAdvanceAvailabilityResolver,
    DestroyPlaceableAvailabilityResolver,
    DropItemAvailabilityResolver,
    GuildAddMemberAvailabilityResolver,
    GuildChangeRoleAvailabilityResolver,
    GuildCreateAvailabilityResolver,
    GuildDepositBankAvailabilityResolver,
    GuildDisbandAvailabilityResolver,
    GuildLeaveAvailabilityResolver,
    GuildWithdrawBankAvailabilityResolver,
    HarvestCancelAvailabilityResolver,
    HarvestStartAvailabilityResolver,
    InspectItemAvailabilityResolver,
    InspectTargetAvailabilityResolver,
    InteractAvailabilityResolver,
    NoOpAvailabilityResolver,
    PlaceObjectAvailabilityResolver,
    PursuitCancelAvailabilityResolver,
    PursuitStartAvailabilityResolver,
    QuestAcceptAvailabilityResolver,
    QuestApproveAvailabilityResolver,
    QuestCancelAvailabilityResolver,
    QuestIssueAvailabilityResolver,
    SayAvailabilityResolver,
    SetDestinationAvailabilityResolver,
    ShopListItemAvailabilityResolver,
    ShopPurchaseAvailabilityResolver,
    ShopUnlistItemAvailabilityResolver,
    MemoryQueryAvailabilityResolver,
    SubagentAvailabilityResolver,
    SkillAcceptProposalAvailabilityResolver,
    SkillActivateAwakenedModeAvailabilityResolver,
    SkillEquipAvailabilityResolver,
    SkillRejectProposalAvailabilityResolver,
    TradeAcceptAvailabilityResolver,
    TradeCancelAvailabilityResolver,
    TradeDeclineAvailabilityResolver,
    TradeOfferAvailabilityResolver,
    SnsToolAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
    WhisperAvailabilityResolver,
    WorkingMemoryAppendAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WORKING_MEMORY_APPEND,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_MOVE_ONE_STEP,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_APPROVE,
    TOOL_NAME_QUEST_CANCEL,
    TOOL_NAME_QUEST_ISSUE,
    TOOL_NAME_SAY,
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SHOP_UNLIST_ITEM,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_LIKE_REPLY,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_UNFOLLOW,
    TOOL_NAME_SNS_SUBSCRIBE,
    TOOL_NAME_SNS_UNSUBSCRIBE,
    TOOL_NAME_SNS_BLOCK,
    TOOL_NAME_SNS_UNBLOCK,
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
    description="指定した目的地（スポット、ロケーション、または視界内オブジェクト）へ移動します。",
    parameters=MOVE_TO_DESTINATION_PARAMETERS,
)

CANCEL_MOVEMENT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CANCEL_MOVEMENT,
    description="設定済みの経路をキャンセルし、移動を中断します。移動中のみ利用可能です。",
    parameters={"type": "object", "properties": {}, "required": []},
)

MOVE_ONE_STEP_PARAMETERS = {
    "type": "object",
    "properties": {
        "direction_label": {
            "type": "string",
            "description": "隣接タイルへ移動する方向。北, 北東, 東, 南東, 南, 南西, 西, 北西 のいずれか。",
        },
    },
    "required": ["direction_label"],
}

MOVE_ONE_STEP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MOVE_ONE_STEP,
    description="指定した方向へ隣接タイルに1歩だけ移動します。最も細かい粒度の移動です。",
    parameters=MOVE_ONE_STEP_PARAMETERS,
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

PURSUIT_START_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示されたプレイヤーまたはモンスターのラベル（例: P1, M1）。",
        },
    },
    "required": ["target_label"],
}

PURSUIT_START_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_PURSUIT_START,
    description="現在見えているプレイヤーまたはモンスターの追跡を開始します。",
    parameters=PURSUIT_START_PARAMETERS,
)

PURSUIT_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_PURSUIT_CANCEL,
    description="現在の追跡を中断します。",
    parameters={"type": "object", "properties": {}, "required": []},
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

SKILL_EQUIP_PARAMETERS = {
    "type": "object",
    "properties": {
        "skill_label": {
            "type": "string",
            "description": "装備候補スキルラベル（例: EK1）。",
        },
        "slot_label": {
            "type": "string",
            "description": "装備先スロットラベル（例: ES1）。",
        },
    },
    "required": ["skill_label", "slot_label"],
}

SKILL_EQUIP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_EQUIP,
    description="装備候補スキルを指定したスロットへ装備します。",
    parameters=SKILL_EQUIP_PARAMETERS,
)

SKILL_ACCEPT_PROPOSAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "proposal_label": {
            "type": "string",
            "description": "受諾するスキル提案ラベル（例: SP1）。",
        },
    },
    "required": ["proposal_label"],
}

SKILL_ACCEPT_PROPOSAL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    description="保留中のスキル進化提案を受諾します。",
    parameters=SKILL_ACCEPT_PROPOSAL_PARAMETERS,
)

SKILL_REJECT_PROPOSAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "proposal_label": {
            "type": "string",
            "description": "却下するスキル提案ラベル（例: SP1）。",
        },
    },
    "required": ["proposal_label"],
}

SKILL_REJECT_PROPOSAL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_REJECT_PROPOSAL,
    description="保留中のスキル進化提案を却下します。",
    parameters=SKILL_REJECT_PROPOSAL_PARAMETERS,
)

SKILL_ACTIVATE_AWAKENED_MODE_PARAMETERS = {
    "type": "object",
    "properties": {
        "awakened_action_label": {
            "type": "string",
            "description": "覚醒モード発動ラベル（例: AW1）。",
        },
    },
    "required": ["awakened_action_label"],
}

SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    description="覚醒モードを発動します。継続時間や消費コストはサーバ側設定に従います。",
    parameters=SKILL_ACTIVATE_AWAKENED_MODE_PARAMETERS,
)

QUEST_ACCEPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "受託するクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}
QUEST_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_ACCEPT,
    description="掲示されているクエストを受託します。",
    parameters=QUEST_ACCEPT_PARAMETERS,
)

QUEST_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "キャンセルするクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}
QUEST_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_CANCEL,
    description="受託中のクエストをキャンセルします。",
    parameters=QUEST_CANCEL_PARAMETERS,
)

QUEST_APPROVE_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "承認するクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}
QUEST_APPROVE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_APPROVE,
    description="ギルド掲示のクエストを承認します（オフィサー以上）。",
    parameters=QUEST_APPROVE_PARAMETERS,
)

QUEST_ISSUE_PARAMETERS = {
    "type": "object",
    "properties": {
        "objectives": {
            "type": "array",
            "description": "クエスト目標のリスト。target_name または target_id のいずれかを指定。target_name はモンスター名・スポット名・アイテム名・プレイヤー名で検索。",
            "items": {
                "type": "object",
                "properties": {
                    "objective_type": {
                        "type": "string",
                        "description": "kill_monster, obtain_item, reach_spot, kill_player（名前解決対応）。talk_to_npc 等は target_id で指定。",
                    },
                    "target_name": {
                        "type": "string",
                        "description": "目標の名前（ゴブリン、北の森、鉄の剣、プレイヤー名 等）。target_id の代わりに指定可能。",
                    },
                    "target_id": {
                        "type": "integer",
                        "description": "目標の ID（モンスター種別、NPC ID、スポット ID 等）。target_name の代わりに指定可能。",
                    },
                    "required_count": {
                        "type": "integer",
                        "description": "必要数",
                    },
                },
                "required": ["objective_type", "required_count"],
            },
        },
        "reward_gold": {"type": "integer", "description": "報酬ゴールド。", "default": 0},
        "reward_items": {
            "type": "array",
            "description": "報酬アイテム。各要素は item_spec_id と quantity を持つオブジェクト。",
            "items": {
                "type": "object",
                "properties": {
                    "item_spec_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                },
                "required": ["item_spec_id", "quantity"],
            },
        },
        "guild_label": {
            "type": "string",
            "description": "ギルド掲示の場合のギルドラベル（例: G1）。省略時は公開クエスト。ギルド依頼はギルドのロケーションにいる場合のみ発行可能。",
        },
    },
    "required": ["objectives"],
}
QUEST_ISSUE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_ISSUE,
    description="クエストを発行します。報酬にゴールド・アイテムを指定可能。guild_label を指定するとギルド掲示（承認待ち）になります。ギルド依頼はギルドのロケーションにいる場合のみ発行可能。",
    parameters=QUEST_ISSUE_PARAMETERS,
)

GUILD_CREATE_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "ギルド名。"},
        "description": {"type": "string", "description": "ギルドの説明。", "default": ""},
    },
    "required": ["name"],
}
GUILD_CREATE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_CREATE,
    description="現在地のロケーションにギルドを作成します。spot_id と location_area_id は現在地から自動取得されます。",
    parameters=GUILD_CREATE_PARAMETERS,
)

GUILD_ADD_MEMBER_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "招待先ギルドラベル（例: G1）。"},
        "target_player_label": {"type": "string", "description": "招待するプレイヤーラベル（例: P1）。"},
    },
    "required": ["guild_label", "target_player_label"],
}
GUILD_ADD_MEMBER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_ADD_MEMBER,
    description="ギルドにプレイヤーを招待します（オフィサー以上）。",
    parameters=GUILD_ADD_MEMBER_PARAMETERS,
)

GUILD_CHANGE_ROLE_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "対象ギルドラベル（例: G1）。"},
        "target_member_label": {"type": "string", "description": "役職変更するメンバーラベル（例: GM1）。"},
        "new_role": {"type": "string", "description": "新しい役職。leader / officer / member のいずれか。", "enum": ["leader", "officer", "member"]},
    },
    "required": ["guild_label", "target_member_label", "new_role"],
}
GUILD_CHANGE_ROLE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_CHANGE_ROLE,
    description="ギルドメンバーの役職を変更します（オフィサー以上）。",
    parameters=GUILD_CHANGE_ROLE_PARAMETERS,
)

GUILD_DISBAND_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "解散するギルドラベル（例: G1）。"},
    },
    "required": ["guild_label"],
}
GUILD_DISBAND_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_DISBAND,
    description="ギルドを解散します（リーダーのみ）。",
    parameters=GUILD_DISBAND_PARAMETERS,
)

GUILD_LEAVE_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "脱退するギルドラベル（例: G1）。"},
    },
    "required": ["guild_label"],
}
GUILD_LEAVE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_LEAVE,
    description="所属ギルドから脱退します。",
    parameters=GUILD_LEAVE_PARAMETERS,
)

GUILD_DEPOSIT_BANK_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "入金先ギルドラベル（例: G1）。"},
        "amount": {"type": "integer", "description": "入金するゴールド量。"},
    },
    "required": ["guild_label", "amount"],
}
GUILD_DEPOSIT_BANK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_DEPOSIT_BANK,
    description="ギルド金庫にゴールドを入金します。",
    parameters=GUILD_DEPOSIT_BANK_PARAMETERS,
)

GUILD_WITHDRAW_BANK_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "出金元ギルドラベル（例: G1）。"},
        "amount": {"type": "integer", "description": "出金するゴールド量。"},
    },
    "required": ["guild_label", "amount"],
}
GUILD_WITHDRAW_BANK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_WITHDRAW_BANK,
    description="ギルド金庫からゴールドを出金します（オフィサー以上）。",
    parameters=GUILD_WITHDRAW_BANK_PARAMETERS,
)

SHOP_PURCHASE_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "購入先ショップラベル（例: SH1）。"},
        "listing_label": {"type": "string", "description": "購入する出品ラベル（例: L1）。プロンプトの近隣ショップ出品一覧から選択。"},
        "listing_id": {"type": "integer", "description": "購入する出品のID。listing_label の代わりに使用可。"},
        "quantity": {"type": "integer", "description": "購入数量。", "default": 1},
    },
    "required": ["shop_label"],
}
SHOP_PURCHASE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_PURCHASE,
    description="ショップでアイテムを購入します。",
    parameters=SHOP_PURCHASE_PARAMETERS,
)

SHOP_LIST_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "出品先ショップラベル（例: SH1）。"},
        "inventory_item_label": {"type": "string", "description": "出品する在庫アイテムラベル（例: I1）。"},
        "price_per_unit": {"type": "integer", "description": "単価（ゴールド）。"},
    },
    "required": ["shop_label", "inventory_item_label", "price_per_unit"],
}
SHOP_LIST_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_LIST_ITEM,
    description="ショップにアイテムを出品します（オーナーのみ）。",
    parameters=SHOP_LIST_ITEM_PARAMETERS,
)

SHOP_UNLIST_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "取り下げ元ショップラベル（例: SH1）。"},
        "listing_label": {"type": "string", "description": "取り下げる出品ラベル（例: L1）。プロンプトの近隣ショップ出品一覧から選択。"},
        "listing_id": {"type": "integer", "description": "取り下げる出品のID。listing_label の代わりに使用可。"},
    },
    "required": ["shop_label"],
}
SHOP_UNLIST_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_UNLIST_ITEM,
    description="ショップの出品を取り下げます（オーナーのみ）。",
    parameters=SHOP_UNLIST_ITEM_PARAMETERS,
)

TRADE_OFFER_PARAMETERS = {
    "type": "object",
    "properties": {
        "inventory_item_label": {"type": "string", "description": "出品する在庫アイテムラベル（例: I1）。"},
        "requested_gold": {"type": "integer", "description": "希望価格（ゴールド）。"},
        "target_player_label": {"type": "string", "description": "宛先プレイヤーラベル（例: P1）。プロンプトの視界内対象から選択。省略時は誰でも受諾可能。"},
        "target_player_id": {"type": "integer", "description": "宛先プレイヤーID。target_player_label の代わりに使用可。", "default": None},
    },
    "required": ["inventory_item_label", "requested_gold"],
}
TRADE_OFFER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_OFFER,
    description="アイテムを他プレイヤーに直接取引で出品します。",
    parameters=TRADE_OFFER_PARAMETERS,
)

TRADE_ACCEPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "受諾する取引ラベル（例: T1）。"},
    },
    "required": ["trade_label"],
}
TRADE_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_ACCEPT,
    description="宛先の取引を受諾して購入します。",
    parameters=TRADE_ACCEPT_PARAMETERS,
)

TRADE_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "キャンセルする取引ラベル（例: T1）。"},
    },
    "required": ["trade_label"],
}
TRADE_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_CANCEL,
    description="自分が発信した取引をキャンセルします。",
    parameters=TRADE_CANCEL_PARAMETERS,
)

TRADE_DECLINE_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "断る取引ラベル（例: T1）。直接取引の宛先のみ使用可能。"},
    },
    "required": ["trade_label"],
}
TRADE_DECLINE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_DECLINE,
    description="自分宛ての取引提案を断ります。直接取引の宛先のみ実行可能。",
    parameters=TRADE_DECLINE_PARAMETERS,
)

# --- SNS ---
SNS_CREATE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "投稿する内容（280文字以内）。"},
        "visibility": {"type": "string", "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。"},
    },
    "required": ["content"],
}
SNS_CREATE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_POST,
    description="SNSに新しい投稿を作成します。",
    parameters=SNS_CREATE_POST_PARAMETERS,
)

SNS_CREATE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "リプライする内容。"},
        "parent_post_id": {"type": "integer", "description": "親ポストのID。parent_reply_id とどちらか必須。"},
        "parent_reply_id": {"type": "integer", "description": "親リプライのID。parent_post_id とどちらか必須。"},
        "visibility": {"type": "string", "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。"},
    },
    "required": ["content"],
}
SNS_CREATE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_REPLY,
    description="ポストまたはリプライに返信します。parent_post_id または parent_reply_id のどちらかを指定してください。",
    parameters=SNS_CREATE_REPLY_PARAMETERS,
)

SNS_LIKE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "post_id": {"type": "integer", "description": "いいねするポストのID。"},
    },
    "required": ["post_id"],
}
SNS_LIKE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_POST,
    description="ポストにいいねします。",
    parameters=SNS_LIKE_POST_PARAMETERS,
)

SNS_LIKE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "reply_id": {"type": "integer", "description": "いいねするリプライのID。"},
    },
    "required": ["reply_id"],
}
SNS_LIKE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_REPLY,
    description="リプライにいいねします。",
    parameters=SNS_LIKE_REPLY_PARAMETERS,
)

SNS_FOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォローするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_FOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_FOLLOW,
    description="指定したユーザーをフォローします。",
    parameters=SNS_FOLLOW_PARAMETERS,
)

SNS_UNFOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォロー解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNFOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNFOLLOW,
    description="指定したユーザーのフォローを解除します。",
    parameters=SNS_UNFOLLOW_PARAMETERS,
)

SNS_SUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_SUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_SUBSCRIBE,
    description="指定したユーザーをサブスクライブします。",
    parameters=SNS_SUBSCRIBE_PARAMETERS,
)

SNS_UNSUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブ解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNSUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNSUBSCRIBE,
    description="指定したユーザーのサブスクライブを解除します。",
    parameters=SNS_UNSUBSCRIBE_PARAMETERS,
)

SNS_BLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロックするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_BLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_BLOCK,
    description="指定したユーザーをブロックします。",
    parameters=SNS_BLOCK_PARAMETERS,
)

SNS_UNBLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロック解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNBLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNBLOCK,
    description="指定したユーザーのブロックを解除します。",
    parameters=SNS_UNBLOCK_PARAMETERS,
)

# --- メモリ・TODO・作業メモ ---
MEMORY_QUERY_PARAMETERS = {
    "type": "object",
    "properties": {
        "expr": {
            "type": "string",
            "description": "DSL 式。例: episodic.take(10), facts.take(5), state",
        },
        "output_mode": {
            "type": "string",
            "enum": ["text", "preview", "count", "handle"],
            "description": "出力形式。text=全文, preview=先頭5件, count=件数のみ, handle=サーバ内参照（subagent で再利用可）",
        },
    },
    "required": ["expr"],
}
MEMORY_QUERY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_QUERY,
    description="メモリ変数（episodic, facts, laws, recent_events, state, working_memory）を DSL 式で検索します。",
    parameters=MEMORY_QUERY_PARAMETERS,
)

SUBAGENT_PARAMETERS = {
    "type": "object",
    "properties": {
        "bindings": {
            "type": "object",
            "description": "名前付き入力。各値は DSL 式または handle:h_xxx。例: {\"episodes\": \"episodic.take(20)\"} または {\"episodes\": \"handle:h_abc123\"}",
        },
        "query": {
            "type": "string",
            "description": "自然言語クエリ。bindings のデータを使って要約・教訓を求めます。",
        },
    },
    "required": ["bindings", "query"],
}
SUBAGENT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SUBAGENT,
    description="絞り込んだメモリを渡し、要約・教訓を取得します（read-only）。",
    parameters=SUBAGENT_PARAMETERS,
)

TODO_ADD_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "TODO の内容"},
    },
    "required": ["content"],
}
TODO_ADD_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_ADD,
    description="TODO を追加します。",
    parameters=TODO_ADD_PARAMETERS,
)

TODO_LIST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_LIST,
    description="未完了の TODO 一覧を取得します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

TODO_COMPLETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "todo_id": {"type": "string", "description": "完了する TODO の ID"},
    },
    "required": ["todo_id"],
}
TODO_COMPLETE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_COMPLETE,
    description="指定した TODO を完了にします。",
    parameters=TODO_COMPLETE_PARAMETERS,
)

WORKING_MEMORY_APPEND_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "追加するテキスト（仮説・メモなど）"},
    },
    "required": ["text"],
}
WORKING_MEMORY_APPEND_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_WORKING_MEMORY_APPEND,
    description="作業メモにテキストを追加します。仮説や中間結論を記録できます。",
    parameters=WORKING_MEMORY_APPEND_PARAMETERS,
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
    drop_enabled: bool = False,
    chest_enabled: bool = False,
    pursuit_enabled: bool = False,
    combat_enabled: bool = False,
    quest_enabled: bool = False,
    guild_enabled: bool = False,
    shop_enabled: bool = False,
    trade_enabled: bool = False,
    sns_enabled: bool = False,
    inspect_item_enabled: bool = False,
    inspect_target_enabled: bool = False,
    memory_query_enabled: bool = False,
    subagent_enabled: bool = False,
    todo_enabled: bool = False,
    working_memory_enabled: bool = False,
) -> None:
    """標準ツール群を登録し、依存サービスがあるカテゴリだけ追加する。"""
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")
    registry.register(NO_OP_DEFINITION, NoOpAvailabilityResolver())
    registry.register(MOVE_TO_DESTINATION_DEFINITION, SetDestinationAvailabilityResolver())
    registry.register(MOVE_ONE_STEP_DEFINITION, MoveOneStepAvailabilityResolver())
    registry.register(CANCEL_MOVEMENT_DEFINITION, CancelMovementAvailabilityResolver())
    if pursuit_enabled:
        registry.register(PURSUIT_START_DEFINITION, PursuitStartAvailabilityResolver())
        registry.register(PURSUIT_CANCEL_DEFINITION, PursuitCancelAvailabilityResolver())
    if speech_enabled:
        registry.register(WHISPER_DEFINITION, WhisperAvailabilityResolver())
        registry.register(SAY_DEFINITION, SayAvailabilityResolver())
    if interaction_enabled:
        registry.register(INTERACT_WORLD_OBJECT_DEFINITION, InteractAvailabilityResolver())
    if inspect_item_enabled:
        registry.register(INSPECT_ITEM_DEFINITION, InspectItemAvailabilityResolver())
    if inspect_target_enabled:
        registry.register(INSPECT_TARGET_DEFINITION, InspectTargetAvailabilityResolver())
    if harvest_enabled:
        registry.register(HARVEST_START_DEFINITION, HarvestStartAvailabilityResolver())
        registry.register(HARVEST_CANCEL_DEFINITION, HarvestCancelAvailabilityResolver())
    if attention_enabled:
        registry.register(CHANGE_ATTENTION_DEFINITION, ChangeAttentionAvailabilityResolver())
    if conversation_enabled:
        registry.register(CONVERSATION_ADVANCE_DEFINITION, ConversationAdvanceAvailabilityResolver())
    if place_enabled:
        registry.register(PLACE_OBJECT_DEFINITION, PlaceObjectAvailabilityResolver())
        registry.register(DESTROY_PLACEABLE_DEFINITION, DestroyPlaceableAvailabilityResolver())
    if drop_enabled:
        registry.register(DROP_ITEM_DEFINITION, DropItemAvailabilityResolver())
    if chest_enabled:
        registry.register(CHEST_STORE_DEFINITION, ChestStoreAvailabilityResolver())
        registry.register(CHEST_TAKE_DEFINITION, ChestTakeAvailabilityResolver())
    if combat_enabled:
        registry.register(COMBAT_USE_SKILL_DEFINITION, CombatUseSkillAvailabilityResolver())
        registry.register(SKILL_EQUIP_DEFINITION, SkillEquipAvailabilityResolver())
        registry.register(
            SKILL_ACCEPT_PROPOSAL_DEFINITION,
            SkillAcceptProposalAvailabilityResolver(),
        )
        registry.register(
            SKILL_REJECT_PROPOSAL_DEFINITION,
            SkillRejectProposalAvailabilityResolver(),
        )
        registry.register(
            SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION,
            SkillActivateAwakenedModeAvailabilityResolver(),
        )
    if quest_enabled:
        registry.register(QUEST_ACCEPT_DEFINITION, QuestAcceptAvailabilityResolver())
        registry.register(QUEST_CANCEL_DEFINITION, QuestCancelAvailabilityResolver())
        registry.register(QUEST_APPROVE_DEFINITION, QuestApproveAvailabilityResolver())
        registry.register(QUEST_ISSUE_DEFINITION, QuestIssueAvailabilityResolver())
    if guild_enabled:
        registry.register(GUILD_CREATE_DEFINITION, GuildCreateAvailabilityResolver())
        registry.register(GUILD_ADD_MEMBER_DEFINITION, GuildAddMemberAvailabilityResolver())
        registry.register(GUILD_CHANGE_ROLE_DEFINITION, GuildChangeRoleAvailabilityResolver())
        registry.register(GUILD_DISBAND_DEFINITION, GuildDisbandAvailabilityResolver())
        registry.register(GUILD_LEAVE_DEFINITION, GuildLeaveAvailabilityResolver())
        registry.register(GUILD_DEPOSIT_BANK_DEFINITION, GuildDepositBankAvailabilityResolver())
        registry.register(GUILD_WITHDRAW_BANK_DEFINITION, GuildWithdrawBankAvailabilityResolver())
    if shop_enabled:
        registry.register(SHOP_PURCHASE_DEFINITION, ShopPurchaseAvailabilityResolver())
        registry.register(SHOP_LIST_ITEM_DEFINITION, ShopListItemAvailabilityResolver())
        registry.register(SHOP_UNLIST_ITEM_DEFINITION, ShopUnlistItemAvailabilityResolver())
    if trade_enabled:
        registry.register(TRADE_OFFER_DEFINITION, TradeOfferAvailabilityResolver())
        registry.register(TRADE_ACCEPT_DEFINITION, TradeAcceptAvailabilityResolver())
        registry.register(TRADE_CANCEL_DEFINITION, TradeCancelAvailabilityResolver())
        registry.register(TRADE_DECLINE_DEFINITION, TradeDeclineAvailabilityResolver())
    if sns_enabled:
        sns_resolver = SnsToolAvailabilityResolver()
        registry.register(SNS_CREATE_POST_DEFINITION, sns_resolver)
        registry.register(SNS_CREATE_REPLY_DEFINITION, sns_resolver)
        registry.register(SNS_LIKE_POST_DEFINITION, sns_resolver)
        registry.register(SNS_LIKE_REPLY_DEFINITION, sns_resolver)
        registry.register(SNS_FOLLOW_DEFINITION, sns_resolver)
        registry.register(SNS_UNFOLLOW_DEFINITION, sns_resolver)
        registry.register(SNS_SUBSCRIBE_DEFINITION, sns_resolver)
        registry.register(SNS_UNSUBSCRIBE_DEFINITION, sns_resolver)
        registry.register(SNS_BLOCK_DEFINITION, sns_resolver)
        registry.register(SNS_UNBLOCK_DEFINITION, sns_resolver)
    if memory_query_enabled:
        registry.register(MEMORY_QUERY_DEFINITION, MemoryQueryAvailabilityResolver())
    if subagent_enabled:
        registry.register(SUBAGENT_DEFINITION, SubagentAvailabilityResolver())
    if todo_enabled:
        registry.register(TODO_ADD_DEFINITION, TodoAddAvailabilityResolver())
        registry.register(TODO_LIST_DEFINITION, TodoListAvailabilityResolver())
        registry.register(TODO_COMPLETE_DEFINITION, TodoCompleteAvailabilityResolver())
    if working_memory_enabled:
        registry.register(
            WORKING_MEMORY_APPEND_DEFINITION,
            WorkingMemoryAppendAvailabilityResolver(),
        )
