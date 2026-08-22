from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
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
    # OBJECT_STATE_INT_AT_LEAST が読む object.state のキー。
    state_key: Optional[str] = None
    # Phase 4-D-1: プレイヤー状態 (needs / HP) 連動の precondition 用フィールド。
    # それぞれ対応する condition_type のときだけ意味を持つ。
    need_type: Optional[str] = None  # PLAYER_NEED_AT_LEAST: "HUNGER" | "FATIGUE" 等
    need_threshold: Optional[int] = None  # PLAYER_NEED_AT_LEAST: この値以上で成立
    gold_threshold: Optional[int] = None  # PLAYER_GOLD_AT_LEAST: この額以上で成立
    hp_ratio: Optional[float] = None  # PLAYER_HP_RATIO_BELOW / _AT_LEAST: 0.0..1.0
    # PR4 (v2 行動制限): 時間帯 / 天候 condition 用フィールド。
    # 対応する condition_type のときだけ意味を持つ:
    #   TIME_OF_DAY_IS{_NOT} → required_time_of_day_phase
    #     ("morning" / "noon" / "evening" / "night" 等、day_night cycle の phase)
    #   WEATHER_IS{_NOT} → required_weather_type
    #     ("CLEAR" / "RAIN" / "STORM" / "FOG")
    required_time_of_day_phase: Optional[str] = None
    required_weather_type: Optional[str] = None
    # 対人インタラクション: 判定する品目を実行時に決めるとき、
    # ``interaction_parameters`` のどのキーを見るかを指す。
    # ``TARGET_HAS_ITEM`` / ``TARGET_HAS_NO_ITEM`` で意味を持つ。
    #
    # 固定の ``target_item_spec_id`` だと、奪える品目のぶんだけ action を並べる
    # ことになり、設計 doc §3.2 で棄却した「同じ行為の複製」になる。倒れた相手
    # の持ち物は prompt に見えている (PR #824) ので、LLM が名指しできる形にする。
    item_spec_id_parameter_key: Optional[str] = None
    # 場所条件 (PR 3) 用フィールド。対応する condition_type のときだけ意味を持つ:
    #   SPOT_LIGHTING_IS{_NOT} → required_lighting ("BRIGHT" / "DIM" / "DARK" /
    #     "PITCH_BLACK")。既存の TIME_OF_DAY / WEATHER と同じ「単一値 + _IS_NOT」
    #     に揃える。設計 doc の草案にあった配列形 (["DARK", "PITCH_BLACK"]) は
    #     採らない。条件を 2 行並べれば同じことが書ける一方、配列形だけが
    #     他の条件と作法が違うと、シナリオ作者もパーサも分岐が増える。
    #   AT_SPOT_IS{_NOT} → required_spot_id
    required_lighting: Optional[str] = None
    required_spot_id: Optional[SpotId] = None

