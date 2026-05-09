from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@dataclass(frozen=True)
class InteractionCondition:
    condition_type: InteractionConditionTypeEnum
    target_item_spec_id: Optional[ItemSpecId] = None
    target_object_id: Optional[SpotObjectId] = None
    required_state: Optional[Dict[str, Any]] = None
    flag_name: Optional[str] = None
    failure_message: str = ""
    # 脱出ゲーム拡張
    required_player_count: Optional[int] = None
    prepared_action_id: Optional[str] = None
    puzzle_input_key: Optional[str] = None
    required_item_spec_ids: Optional[Tuple[ItemSpecId, ...]] = None
    # 数量セマンティクス (Phase 2-A)
    # HAS_ITEM の最低必要個数。default 1 で既存挙動と互換。
    # HAS_ITEMS は「各 spec を quantity 個ずつ」とし、種ごとに別 quantity を
    # 表現したい場合は HAS_ITEM を複数列挙する想定。
    required_quantity: int = 1
    # Phase 4-D-1: プレイヤー状態 (needs / HP) 連動の precondition 用フィールド。
    # それぞれ対応する condition_type のときだけ意味を持つ。
    need_type: Optional[str] = None  # PLAYER_NEED_AT_LEAST: "HUNGER" | "FATIGUE" 等
    need_threshold: Optional[int] = None  # PLAYER_NEED_AT_LEAST: この値以上で成立
    hp_ratio: Optional[float] = None  # PLAYER_HP_RATIO_BELOW / _AT_LEAST: 0.0..1.0
