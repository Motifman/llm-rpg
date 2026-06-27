"""LLM 向け表示・記憶層の DTO"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


# 再スケジュール対象とする error_code（1起動1ツール前提で次tickで再試行する）
# LLM_AUTHENTICATION_ERROR は恒久障害のため除外
_RESCHEDULE_ERROR_CODES = frozenset({
    "NO_TOOL_CALL",           # LLM がツールを返さなかった
    "LLM_API_CALL_FAILED",    # 一時的 API 失敗
    "LLM_RATE_LIMIT",         # レート制限
    "INVALID_DESTINATION_LABEL",  # ラベル未解決（次 tick で解消の可能性）
    # PR-J: LLM の tool 名 typo (e.g. speech_speech / spot_graph_gather) を救済
    # する。エラーメッセージに fuzzy suggestion + valid 一覧を載せて agent に
    # 修正させるため、次 tick での起床が必須。5 連続 typo すれば PR-I の
    # self-reschedule streak が soft cap として効いて chain は終わる。
    # ※ PR-I で schedule_turn は streak を一切触らない設計なので、他者観測
    #   経由の ping-pong が混ざっても streak はリセットされず、典型 typo loop
    #   は確実に 5 wave で止まる。
    "UNSUPPORTED_TOOL",
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

    ``omit_result_in_prompt``: True にすると、成功時にプロンプトの「直近の出来事」
    セクションで ``→ [結果] {result_summary}`` 部分を省略する (Issue #188 改善)。
    速度速報のような自明な結果 (例: ``speech_say`` の「発言しました。」) は LLM
    に情報を足さないため、ノイズを減らすために省略できるようにする。
    失敗時は省略せず remediation を必ず見せる (LLM が修正できるように)。
    """

    success: bool
    message: str
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    should_reschedule: bool = False
    was_no_op: bool = False
    omit_result_in_prompt: bool = False

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
        if not isinstance(self.omit_result_in_prompt, bool):
            raise TypeError("omit_result_in_prompt must be bool")


@dataclass(frozen=True)
class SystemPromptPlayerInfoDto:
    """システムプロンプト生成用のプレイヤー情報 DTO"""

    player_name: str
    role: str
    race: str
    element: str
    game_description: str
    persona_block: str = ""

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
        if not isinstance(self.persona_block, str):
            raise TypeError("persona_block must be str")


@dataclass(frozen=True)
class ActionResultEntry:
    """行動結果 1 件（直近の出来事のマージ用）。

    ``game_time_label`` は観測との時刻表示の対称性のため (Issue #188 改善)。
    ``omit_result_in_prompt`` は成功時の result_summary 省略フラグ。
    どちらも既定 None / False で後方互換。
    """

    occurred_at: datetime
    action_summary: str
    result_summary: str
    success: bool = True
    error_code: Optional[str] = None
    tool_name: Optional[str] = None
    argument_fingerprint: Optional[str] = None
    should_reschedule: bool = False
    game_time_label: Optional[str] = None
    omit_result_in_prompt: bool = False
    # 予測→学習ループの主観入力。次ターン feedback (PR1) では expected_result のみ
    # 使うが、episodic 永続化 (PR2) で intention→episode.why / expected_result→
    # episode.expected / emotion_hint→episode.felt に配線する。どれも既定 None で
    # 後方互換 (= world-action 以外の tool / 旧 snapshot)。
    expected_result: Optional[str] = None
    intention: Optional[str] = None
    emotion_hint: Optional[str] = None
    # Issue #311 後続: エピソード記憶のチャンク境界判定で「シーン切り替え」を
    # 明示的に伝えるためのヒント。``True`` の action が bucket に入ったら
    # chunk を閉じる候補とする (cognitive science の "doorway effect" 等を
    # 反映)。spot 遷移成功や重要な interaction 等の caller が True にする。
    # 未指定 (False) の action はチャンク化に対して中立 = 従来の境界条件で判定。
    scene_boundary: bool = False
    # action が起きた時点のゲーム内 tick (記録時点で取れない caller は None)。
    # ``decide_chunk_boundary`` の TEMPORAL_GAP 判定で bucket 内 actions の
    # tick 差を見るのに使う (wall-clock では LLM レイテンシで歪むため)。
    occurred_tick: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(self.result_summary, str):
            raise TypeError("result_summary must be str")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        if self.tool_name is not None and not isinstance(self.tool_name, str):
            raise TypeError("tool_name must be str or None")
        if self.argument_fingerprint is not None and not isinstance(
            self.argument_fingerprint, str
        ):
            raise TypeError("argument_fingerprint must be str or None")
        if not isinstance(self.should_reschedule, bool):
            raise TypeError("should_reschedule must be bool")
        if self.game_time_label is not None and not isinstance(
            self.game_time_label, str
        ):
            raise TypeError("game_time_label must be str or None")
        if not isinstance(self.omit_result_in_prompt, bool):
            raise TypeError("omit_result_in_prompt must be bool")
        if self.expected_result is not None and not isinstance(self.expected_result, str):
            raise TypeError("expected_result must be str or None")
        if self.intention is not None and not isinstance(self.intention, str):
            raise TypeError("intention must be str or None")
        if self.emotion_hint is not None and not isinstance(self.emotion_hint, str):
            raise TypeError("emotion_hint must be str or None")
        if not isinstance(self.scene_boundary, bool):
            raise TypeError("scene_boundary must be bool")
        if self.occurred_tick is not None and not isinstance(self.occurred_tick, int):
            raise TypeError("occurred_tick must be int or None")
        if isinstance(self.occurred_tick, bool):
            # bool は int の subclass。tick として誤注入されないよう弾く
            raise TypeError("occurred_tick must not be bool")


EMOTION_HINT_VALUES: Tuple[str, ...] = (
    "curiosity",
    "caution",
    "fear",
    "anxiety",
    "urgency",
    "relief",
    "hope",
    "frustration",
    "confusion",
    "trust",
    "distrust",
    "determination",
    "regret",
    "surprise",
    "neutral",
)



@dataclass(frozen=True)
class ToolDefinitionDto:
    """1 つのツール定義（OpenAI tools 形式の name / description / parameters 用）。"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    category: ToolCategory = field(default=ToolCategory.WORLD_ACTION)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be str")
        if not isinstance(self.description, str):
            raise TypeError("description must be str")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be dict")
        if not isinstance(self.category, ToolCategory):
            if isinstance(self.category, str):
                object.__setattr__(self, "category", ToolCategory(self.category))
            else:
                raise TypeError("category must be ToolCategory")


@dataclass(frozen=True)
class ToolRuntimeTargetDto:
    """一時ラベルから内部IDへ解決するためのターゲット情報。

    物理マップのロケーションエリアIDとスポットグラフのサブロケーションIDは別物のためフィールドを分離する。
    """

    label: str
    kind: str
    display_name: str
    player_id: Optional[int] = None
    world_object_id: Optional[int] = None
    spot_id: Optional[int] = None
    tile_location_area_id: Optional[int] = None
    sub_location_id: Optional[int] = None
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
    # NOTE: 既存 spot_graph_use_item は item_instance_id フィールドに item_spec_id を
    # 入れる旧慣習を持っており (見た目と中身が乖離)、変更すると use_item の挙動が壊れ
    # る。新しい drop_item / pickup_item ツールは「本物の」item_instance_id が要るの
    # で、別フィールド real_item_instance_id を導入する。将来 use_item を直すときに
    # 旧 item_instance_id フィールドを整理する想定 (TODO: rename or migrate)。
    real_item_instance_id: Optional[int] = None
    inventory_slot_id: Optional[int] = None
    chest_world_object_id: Optional[int] = None
    conversation_choice_index: Optional[int] = None
    skill_loadout_id: Optional[int] = None
    skill_slot_index: Optional[int] = None
    skill_id: Optional[int] = None
    deck_tier: Optional[DeckTier] = None
    progress_id: Optional[int] = None
    proposal_id: Optional[int] = None
    target_slot_index: Optional[int] = None
    target_slot_display_name: Optional[str] = None
    attention_level_value: Optional[str] = None
    quest_id: Optional[int] = None
    guild_id: Optional[int] = None
    shop_id: Optional[int] = None
    trade_id: Optional[int] = None
    listing_id: Optional[int] = None
    # スポットグラフ上のモンスター個体ID。world_object_id とは別軸で管理される
    # 個体識別子で、attack 等の戦闘ツールが target_label からモンスターを解決
    # する際に使う（戦闘ツールは別 PR）。2D map 経路は引き続き world_object_id を使う。
    monster_id: Optional[int] = None

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
        if self.tile_location_area_id is not None and not isinstance(
            self.tile_location_area_id, int
        ):
            raise TypeError("tile_location_area_id must be int or None")
        if self.sub_location_id is not None and not isinstance(self.sub_location_id, int):
            raise TypeError("sub_location_id must be int or None")
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
        if self.real_item_instance_id is not None and not isinstance(
            self.real_item_instance_id, int
        ):
            raise TypeError("real_item_instance_id must be int or None")
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
        if self.skill_id is not None and not isinstance(self.skill_id, int):
            raise TypeError("skill_id must be int or None")
        if self.deck_tier is not None and not isinstance(self.deck_tier, DeckTier):
            raise TypeError("deck_tier must be DeckTier or None")
        if self.progress_id is not None and not isinstance(self.progress_id, int):
            raise TypeError("progress_id must be int or None")
        if self.proposal_id is not None and not isinstance(self.proposal_id, int):
            raise TypeError("proposal_id must be int or None")
        if self.target_slot_index is not None and not isinstance(self.target_slot_index, int):
            raise TypeError("target_slot_index must be int or None")
        if self.target_slot_display_name is not None and not isinstance(
            self.target_slot_display_name, str
        ):
            raise TypeError("target_slot_display_name must be str or None")
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
        if self.monster_id is not None and not isinstance(self.monster_id, int):
            raise TypeError("monster_id must be int or None")
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
class SkillEquipCandidateToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """装備候補スキル用の runtime target。"""


@dataclass(frozen=True)
class SkillEquipSlotToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """装備先スロット用の runtime target。"""


@dataclass(frozen=True)
class SkillProposalToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """スキル提案用の runtime target。"""


@dataclass(frozen=True)
class AwakenedActionToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """覚醒モード発動用の runtime target。"""


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
    current_sub_location_id: Optional[int] = None
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
            ("current_sub_location_id", self.current_sub_location_id),
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


# NOTE (Issue #470 Phase 1 PR3):
# MemoEntry / MemoFulfillmentContext / TodoEntry (旧名 alias) は
# ``domain/memory/memo/value_object/`` に昇格しました。
# 新規コードは:
#     from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
# から import してください。
