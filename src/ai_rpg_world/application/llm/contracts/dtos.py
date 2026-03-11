"""LLM 向け表示・記憶層の DTO"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple


# 再スケジュール対象とする error_code（1起動1ツール前提で次tickで再試行する）
# LLM_AUTHENTICATION_ERROR は恒久障害のため除外
_RESCHEDULE_ERROR_CODES = frozenset({
    "NO_TOOL_CALL",           # LLM がツールを返さなかった
    "LLM_API_CALL_FAILED",    # 一時的 API 失敗
    "LLM_RATE_LIMIT",         # レート制限
    "INVALID_DESTINATION_LABEL",  # ラベル未解決（次 tick で解消の可能性）
})


def should_reschedule_for_next_tick(dto: "LlmCommandResultDto") -> bool:
    """
    LlmCommandResultDto から次 tick で再スケジュールすべきか判定する。
    1起動1ツール前提の保守的継続契約に従う。
    """
    if dto.success:
        return False
    return is_reschedulable_error_code(dto.error_code)


def is_reschedulable_error_code(error_code: Optional[str]) -> bool:
    """error_code が再スケジュール対象かどうか。1起動1ツール前提の継続契約用。"""
    return error_code is not None and error_code in _RESCHEDULE_ERROR_CODES


@dataclass(frozen=True)
class LlmCommandResultDto:
    """
    オーケストレータがツール実行結果を IActionResultStore に渡す際の標準形。
    成功時は message に成功メッセージ、失敗時は message にエラー内容、remediation に対処ヒントを入れる。
    should_reschedule: 次 tick で再スケジュールすべきか（1起動1ツール前提の継続契約用）。
    """

    success: bool
    message: str
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    should_reschedule: bool = False
    was_no_op: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if not isinstance(self.message, str):
            raise TypeError("message must be str")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        if self.remediation is not None and not isinstance(self.remediation, str):
            raise TypeError("remediation must be str or None")
        if not isinstance(self.should_reschedule, bool):
            raise TypeError("should_reschedule must be bool")
        if not isinstance(self.was_no_op, bool):
            raise TypeError("was_no_op must be bool")


@dataclass(frozen=True)
class SystemPromptPlayerInfoDto:
    """システムプロンプト生成用のプレイヤー情報 DTO"""

    player_name: str
    role: str
    race: str
    element: str
    game_description: str

    def __post_init__(self) -> None:
        if not isinstance(self.player_name, str):
            raise TypeError("player_name must be str")
        if not isinstance(self.role, str):
            raise TypeError("role must be str")
        if not isinstance(self.race, str):
            raise TypeError("race must be str")
        if not isinstance(self.element, str):
            raise TypeError("element must be str")
        if not isinstance(self.game_description, str):
            raise TypeError("game_description must be str")


@dataclass(frozen=True)
class ActionResultEntry:
    """行動結果 1 件（直近の出来事のマージ用）"""

    occurred_at: datetime
    action_summary: str
    result_summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(self.result_summary, str):
            raise TypeError("result_summary must be str")


@dataclass(frozen=True)
class ToolDefinitionDto:
    """1 つのツール定義（OpenAI tools 形式の name / description / parameters 用）。"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be str")
        if not isinstance(self.description, str):
            raise TypeError("description must be str")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be dict")


@dataclass(frozen=True)
class ToolRuntimeTargetDto:
    """一時ラベルから内部IDへ解決するためのターゲット情報。"""

    label: str
    kind: str
    display_name: str
    player_id: Optional[int] = None
    world_object_id: Optional[int] = None
    spot_id: Optional[int] = None
    location_area_id: Optional[int] = None
    destination_type: Optional[str] = None
    distance: Optional[int] = None
    direction: Optional[str] = None
    target_x: Optional[int] = None
    target_y: Optional[int] = None
    target_z: Optional[int] = None
    relative_dx: Optional[int] = None
    relative_dy: Optional[int] = None
    relative_dz: Optional[int] = None
    interaction_type: Optional[str] = None
    available_interactions: Tuple[str, ...] = ()
    item_instance_id: Optional[int] = None
    inventory_slot_id: Optional[int] = None
    chest_world_object_id: Optional[int] = None
    conversation_choice_index: Optional[int] = None
    skill_loadout_id: Optional[int] = None
    skill_slot_index: Optional[int] = None
    attention_level_value: Optional[str] = None
    quest_id: Optional[int] = None
    guild_id: Optional[int] = None
    shop_id: Optional[int] = None
    trade_id: Optional[int] = None
    listing_id: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.label, str):
            raise TypeError("label must be str")
        if not isinstance(self.kind, str):
            raise TypeError("kind must be str")
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be str")
        if self.player_id is not None and not isinstance(self.player_id, int):
            raise TypeError("player_id must be int or None")
        if self.world_object_id is not None and not isinstance(self.world_object_id, int):
            raise TypeError("world_object_id must be int or None")
        if self.spot_id is not None and not isinstance(self.spot_id, int):
            raise TypeError("spot_id must be int or None")
        if self.location_area_id is not None and not isinstance(self.location_area_id, int):
            raise TypeError("location_area_id must be int or None")
        if self.destination_type is not None and not isinstance(self.destination_type, str):
            raise TypeError("destination_type must be str or None")
        if self.distance is not None and not isinstance(self.distance, int):
            raise TypeError("distance must be int or None")
        if self.direction is not None and not isinstance(self.direction, str):
            raise TypeError("direction must be str or None")
        if self.target_x is not None and not isinstance(self.target_x, int):
            raise TypeError("target_x must be int or None")
        if self.target_y is not None and not isinstance(self.target_y, int):
            raise TypeError("target_y must be int or None")
        if self.target_z is not None and not isinstance(self.target_z, int):
            raise TypeError("target_z must be int or None")
        if self.relative_dx is not None and not isinstance(self.relative_dx, int):
            raise TypeError("relative_dx must be int or None")
        if self.relative_dy is not None and not isinstance(self.relative_dy, int):
            raise TypeError("relative_dy must be int or None")
        if self.relative_dz is not None and not isinstance(self.relative_dz, int):
            raise TypeError("relative_dz must be int or None")
        if self.interaction_type is not None and not isinstance(self.interaction_type, str):
            raise TypeError("interaction_type must be str or None")
        if self.item_instance_id is not None and not isinstance(self.item_instance_id, int):
            raise TypeError("item_instance_id must be int or None")
        if self.inventory_slot_id is not None and not isinstance(self.inventory_slot_id, int):
            raise TypeError("inventory_slot_id must be int or None")
        if self.chest_world_object_id is not None and not isinstance(self.chest_world_object_id, int):
            raise TypeError("chest_world_object_id must be int or None")
        if self.conversation_choice_index is not None and not isinstance(
            self.conversation_choice_index, int
        ):
            raise TypeError("conversation_choice_index must be int or None")
        if self.skill_loadout_id is not None and not isinstance(self.skill_loadout_id, int):
            raise TypeError("skill_loadout_id must be int or None")
        if self.skill_slot_index is not None and not isinstance(self.skill_slot_index, int):
            raise TypeError("skill_slot_index must be int or None")
        if self.attention_level_value is not None and not isinstance(
            self.attention_level_value, str
        ):
            raise TypeError("attention_level_value must be str or None")
        if self.quest_id is not None and not isinstance(self.quest_id, int):
            raise TypeError("quest_id must be int or None")
        if self.guild_id is not None and not isinstance(self.guild_id, int):
            raise TypeError("guild_id must be int or None")
        if self.shop_id is not None and not isinstance(self.shop_id, int):
            raise TypeError("shop_id must be int or None")
        if self.trade_id is not None and not isinstance(self.trade_id, int):
            raise TypeError("trade_id must be int or None")
        if self.listing_id is not None and not isinstance(self.listing_id, int):
            raise TypeError("listing_id must be int or None")
        if not isinstance(self.available_interactions, tuple):
            raise TypeError("available_interactions must be tuple")
        for value in self.available_interactions:
            if not isinstance(value, str):
                raise TypeError("available_interactions must contain only str")


@dataclass(frozen=True)
class VisibleToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """視界内対象用の runtime target。"""


@dataclass(frozen=True)
class PlayerToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """プレイヤー対象用の runtime target。"""


@dataclass(frozen=True)
class NpcToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """NPC 対象用の runtime target。"""


@dataclass(frozen=True)
class MonsterToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """モンスター対象用の runtime target。"""


@dataclass(frozen=True)
class ChestToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """チェスト対象用の runtime target。"""


@dataclass(frozen=True)
class ResourceToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """採集対象用の runtime target。"""


@dataclass(frozen=True)
class ActiveHarvestToolRuntimeTargetDto(ResourceToolRuntimeTargetDto):
    """進行中採集対象用の runtime target。"""


@dataclass(frozen=True)
class WorldObjectToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """一般的な相互作用対象用の runtime target。"""


@dataclass(frozen=True)
class DestinationToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """移動先用の runtime target。"""


@dataclass(frozen=True)
class InventoryToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """インベントリアイテム用の runtime target。"""

    is_placeable: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.is_placeable, bool):
            raise TypeError("is_placeable must be bool")


@dataclass(frozen=True)
class ChestItemToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """チェスト内アイテム用の runtime target。"""


@dataclass(frozen=True)
class ConversationChoiceToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """会話選択肢用の runtime target。"""


@dataclass(frozen=True)
class SkillToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """スキル用の runtime target。"""


@dataclass(frozen=True)
class AttentionLevelToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """注意レベル用の runtime target。"""


@dataclass(frozen=True)
class QuestToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """クエスト用の runtime target。quest_id を持つ。"""


@dataclass(frozen=True)
class GuildToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ギルド用の runtime target。guild_id を持つ。"""


@dataclass(frozen=True)
class ShopToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ショップ用の runtime target。shop_id を持つ。"""


@dataclass(frozen=True)
class ShopListingToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ショップ出品用の runtime target。shop_id と listing_id を持つ。"""


@dataclass(frozen=True)
class TradeToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """取引用の runtime target。trade_id を持つ。"""


@dataclass(frozen=True)
class ToolRuntimeContextDto:
    """LLM UIのそのターン限定ラベル解決コンテキスト。"""

    targets: Dict[str, ToolRuntimeTargetDto]
    current_x: Optional[int] = None
    current_y: Optional[int] = None
    current_z: Optional[int] = None
    current_spot_id: Optional[int] = None
    current_area_ids: Optional[Tuple[int, ...]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.targets, dict):
            raise TypeError("targets must be dict")
        for label, target in self.targets.items():
            if not isinstance(label, str):
                raise TypeError("targets keys must be str")
            if not isinstance(target, ToolRuntimeTargetDto):
                raise TypeError("targets values must be ToolRuntimeTargetDto")
        for name, value in (
            ("current_x", self.current_x),
            ("current_y", self.current_y),
            ("current_z", self.current_z),
            ("current_spot_id", self.current_spot_id),
        ):
            if value is not None and not isinstance(value, int):
                raise TypeError(f"{name} must be int or None")
        if self.current_area_ids is not None and not isinstance(self.current_area_ids, tuple):
            raise TypeError("current_area_ids must be tuple or None")
        if self.current_area_ids is not None:
            for x in self.current_area_ids:
                if not isinstance(x, int):
                    raise TypeError("current_area_ids must contain only int")

    @classmethod
    def empty(cls) -> "ToolRuntimeContextDto":
        return cls(targets={})


@dataclass(frozen=True)
class LlmUiContextDto:
    """LLM に見せる現在状態テキストと、内部用のツール実行コンテキスト。"""

    current_state_text: str
    tool_runtime_context: ToolRuntimeContextDto

    def __post_init__(self) -> None:
        if not isinstance(self.current_state_text, str):
            raise TypeError("current_state_text must be str")
        if not isinstance(self.tool_runtime_context, ToolRuntimeContextDto):
            raise TypeError("tool_runtime_context must be ToolRuntimeContextDto")


# ToolAvailabilityContext は PlayerCurrentStateDto をそのまま利用する。
# ツールの利用可否判定に必要な現在地・接続先・視界・移動先等はすべて PlayerCurrentStateDto に含まれる。

# --- 記憶モジュール（Phase 4）---

EpisodeImportance = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class MemoryRetrievalQueryDto:
    """
    予測記憶検索用のクエリ DTO。
    PlayerCurrentStateDto 由来の spot/notable/actionable と tool_names を渡すことで、
    current_state_text の文字面依存を弱める。
    検索優先度: world_object_ids > scope_keys > spot_ids > entity_ids > location_ids
    > actionable/notable > action_names > free_text_keywords
    scope_keys: 関係性メモリ用。例: quest:12, guild:3, shop:9, conversation:npc:42
    """

    entity_ids: Tuple[str, ...] = ()
    location_ids: Tuple[str, ...] = ()
    notable_labels: Tuple[str, ...] = ()
    actionable_labels: Tuple[str, ...] = ()
    action_names: Tuple[str, ...] = ()
    free_text_keywords: Tuple[str, ...] = ()
    world_object_ids: Tuple[int, ...] = ()
    spot_ids: Tuple[int, ...] = ()
    scope_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, val in [
            ("entity_ids", self.entity_ids),
            ("location_ids", self.location_ids),
            ("notable_labels", self.notable_labels),
            ("actionable_labels", self.actionable_labels),
            ("action_names", self.action_names),
            ("free_text_keywords", self.free_text_keywords),
            ("scope_keys", self.scope_keys),
        ]:
            if not isinstance(val, tuple):
                raise TypeError(f"{name} must be tuple")
            for x in val:
                if not isinstance(x, str):
                    raise TypeError(f"{name} must contain only str")
        if not isinstance(self.world_object_ids, tuple):
            raise TypeError("world_object_ids must be tuple")
        for x in self.world_object_ids:
            if not isinstance(x, int):
                raise TypeError("world_object_ids must contain only int")
        if not isinstance(self.spot_ids, tuple):
            raise TypeError("spot_ids must be tuple")
        for x in self.spot_ids:
            if not isinstance(x, int):
                raise TypeError("spot_ids must contain only int")


@dataclass(frozen=True)
class EpisodeMemoryEntry:
    """エピソード記憶 1 件（記憶抽出の出力・ストアの保存単位）。
    world_object_ids, spot_id_value は stable id 検索用。display name は entity_ids, location_id に保持。
    scope_keys は関係性メモリ用。例: quest:12, guild:3, shop:9, conversation:npc:42
    """

    id: str
    context_summary: str
    action_taken: str
    outcome_summary: str
    entity_ids: Tuple[str, ...]
    location_id: Optional[str]
    timestamp: datetime
    importance: EpisodeImportance
    surprise: bool
    recall_count: int
    world_object_ids: Tuple[int, ...] = ()
    spot_id_value: Optional[int] = None
    scope_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.context_summary, str):
            raise TypeError("context_summary must be str")
        if not isinstance(self.action_taken, str):
            raise TypeError("action_taken must be str")
        if not isinstance(self.outcome_summary, str):
            raise TypeError("outcome_summary must be str")
        if not isinstance(self.entity_ids, tuple):
            raise TypeError("entity_ids must be tuple")
        for x in self.entity_ids:
            if not isinstance(x, str):
                raise TypeError("entity_ids must contain only str")
        if self.location_id is not None and not isinstance(self.location_id, str):
            raise TypeError("location_id must be str or None")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime")
        if self.importance not in ("low", "medium", "high"):
            raise TypeError("importance must be 'low', 'medium', or 'high'")
        if not isinstance(self.surprise, bool):
            raise TypeError("surprise must be bool")
        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise TypeError("recall_count must be non-negative int")
        if not isinstance(self.world_object_ids, tuple):
            raise TypeError("world_object_ids must be tuple")
        for x in self.world_object_ids:
            if not isinstance(x, int):
                raise TypeError("world_object_ids must contain only int")
        if self.spot_id_value is not None and not isinstance(self.spot_id_value, int):
            raise TypeError("spot_id_value must be int or None")
        if not isinstance(self.scope_keys, tuple):
            raise TypeError("scope_keys must be tuple")
        for x in self.scope_keys:
            if not isinstance(x, str):
                raise TypeError("scope_keys must contain only str")


@dataclass(frozen=True)
class LongTermFactEntry:
    """長期記憶（事実・教訓）1 件。"""

    id: str
    content: str
    player_id: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be datetime")


@dataclass(frozen=True)
class MemoryLawEntry:
    """長期記憶（法則・共起）1 件。主体–関係–対象＋強度。"""

    id: str
    subject: str
    relation: str
    target: str  # 対象
    strength: float
    player_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.subject, str):
            raise TypeError("subject must be str")
        if not isinstance(self.relation, str):
            raise TypeError("relation must be str")
        if not isinstance(self.target, str):
            raise TypeError("target must be str")
        if not isinstance(self.strength, (int, float)):
            raise TypeError("strength must be int or float")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")


@dataclass(frozen=True)
class SubagentEvidenceEntry:
    """subagent の evidence 1 件。"""

    binding_name: str
    source_var: str
    entry_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.binding_name, str):
            raise TypeError("binding_name must be str")
        if not isinstance(self.source_var, str):
            raise TypeError("source_var must be str")
        if not isinstance(self.entry_ids, tuple):
            raise TypeError("entry_ids must be tuple")
        for x in self.entry_ids:
            if not isinstance(x, str):
                raise TypeError("entry_ids must contain only str")


@dataclass(frozen=True)
class SubagentResultDto:
    """subagent の返却値。"""

    answer_summary: str
    evidence: Tuple[SubagentEvidenceEntry, ...]
    used_bindings: Tuple[str, ...]
    truncation_note: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.answer_summary, str):
            raise TypeError("answer_summary must be str")
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be tuple")
        if not isinstance(self.used_bindings, tuple):
            raise TypeError("used_bindings must be tuple")
        for x in self.used_bindings:
            if not isinstance(x, str):
                raise TypeError("used_bindings must contain only str")
        if self.truncation_note is not None and not isinstance(
            self.truncation_note, str
        ):
            raise TypeError("truncation_note must be str or None")


@dataclass(frozen=True)
class TodoEntry:
    """TODO 1 件。LLM が管理するタスクリスト用。"""

    id: str
    content: str
    added_at: datetime
    completed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.added_at, datetime):
            raise TypeError("added_at must be datetime")
        if not isinstance(self.completed, bool):
            raise TypeError("completed must be bool")
