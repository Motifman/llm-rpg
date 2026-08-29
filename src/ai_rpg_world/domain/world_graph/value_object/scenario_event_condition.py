from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotGraphDomainException,
)
from ai_rpg_world.domain.common.exception import ValidationException


# 合成条件のタイプ。leaf 条件と区別するため module-level 定数として明示。
COMPOSITE_CONDITION_TYPES = frozenset({"NOT", "AND", "OR"})
LEAF_CONDITION_TYPES = frozenset({
    "PROBABILITY",
    "TICK_AT_LEAST",
    "TICK_BETWEEN",
    "FLAG_SET",
    "FLAG_NOT_SET",
    "PLAYER_AT_SPOT",
    "PLAYERS_AT_SPOT",
    "GAME_PHASE_IS",
    "OBJECT_STATE",
    "HAS_ITEM",
    "TICK_MODULO",
    "WEATHER_IS",
    "OBJECT_STATE_TICK_AT_LEAST",
    "OBJECT_STATE_INT_AT_LEAST",
    "OBJECT_STATE_INT_GREATER_THAN_OTHER",
})
SUPPORTED_CONDITION_TYPES = COMPOSITE_CONDITION_TYPES | LEAF_CONDITION_TYPES


class ScenarioEventConditionValidationException(SpotGraphDomainException, ValidationException):
    """ScenarioEventCondition のバリデーション例外。"""
    error_code = "WORLD_GRAPH.SCENARIO_EVENT_CONDITION_VALIDATION"


@dataclass(frozen=True)
class ScenarioEventCondition:
    """シナリオ自律イベントの発火条件。

    leaf 条件（TICK_AT_LEAST, FLAG_SET, PLAYER_AT_SPOT など）と、
    合成条件（NOT/AND/OR）を 1 つのデータ構造で表現する。

    合成条件は `children` を使う:
    - NOT: children は 1 個ちょうど。その否定。
    - AND: children 全てが真なら真。空なら真（vacuous truth）。
    - OR : children のどれか 1 つが真なら真。空なら偽。

    leaf 条件は従来通り condition_type と該当フィールドで指定する。
    """

    condition_type: str
    tick: Optional[int] = None
    tick_start: Optional[int] = None
    tick_end: Optional[int] = None
    flag_name: Optional[str] = None
    spot_id: Optional[int] = None
    # PLAYERS_AT_SPOT 用。省略時は interaction 条件の既存意味と同じ 2 人。
    required_player_count: Optional[int] = None
    # GAME_PHASE_IS 用。GamePhase.value を保持する。
    game_phase: Optional[str] = None
    object_id: Optional[int] = None
    required_state: Optional[dict[str, Any]] = None
    item_spec_id: Optional[int] = None
    # 脱出ゲーム拡張: 周期的イベント
    tick_modulo: Optional[int] = None
    tick_phase: Optional[int] = None
    # 動的世界系: 天候 / オブジェクト state 経過
    weather_type: Optional[str] = None  # WEATHER_IS 用 ("RAIN" / "STORM" 等)
    state_key: Optional[str] = None  # OBJECT_STATE_TICK_AT_LEAST の対象 state キー
    ticks_offset: Optional[int] = None  # OBJECT_STATE_TICK_AT_LEAST の経過 tick
    # OBJECT_STATE_TICK_AT_LEAST で state[state_key] が None / 不在の時の解釈。
    # default False: 「まだ起きていない → 経過判定不能 → predicate False」
    # （安全側、たとえば「採取してから N tick 経った」を判定する用途では妥当）。
    # True にすると「起きていない = 過去無限 → predicate True」として扱う
    # （「初期は ripe / clean」を sentinel マジックナンバー無しで表現できる）。
    treat_missing_as_passed: bool = False
    # OBJECT_STATE_INT_GREATER_THAN_OTHER 用: 比較の右辺になる別オブジェクト。
    # 「東の祭壇の納品数 > 西の祭壇の納品数」のように、2 つの object.state の
    # 整数値どうしを比べる (左辺は object_id / state_key を流用)。
    other_object_id: Optional[int] = None
    other_state_key: Optional[str] = None
    # Phase D-1: 確率トリガ用。PROBABILITY condition_type のときに使う [0.0, 1.0]。
    # 評価のたびに random.random() < probability で発火判定する。
    # condition_type が PROBABILITY 以外でこの値が設定されていても無視される。
    probability: Optional[float] = None
    # 合成条件用の子条件ツリー
    children: Tuple["ScenarioEventCondition", ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # children は frozen dataclass の hash 不変条件を保つため必ず tuple。
        # list 等の mutable な型を許すと dataclass の hash() が壊れる。
        if not isinstance(self.children, tuple):
            raise ScenarioEventConditionValidationException(
                f"children must be a tuple, got {type(self.children).__name__}"
            )
        if self.condition_type == "NOT" and len(self.children) != 1:
            raise ScenarioEventConditionValidationException(
                f"NOT condition requires exactly 1 child, got {len(self.children)}"
            )
        if self.condition_type not in COMPOSITE_CONDITION_TYPES and self.children:
            raise ScenarioEventConditionValidationException(
                f"leaf condition '{self.condition_type}' must not have children"
            )
        # PROBABILITY のとき probability は必須かつ [0.0, 1.0]
        if self.condition_type == "PROBABILITY":
            if self.probability is None:
                raise ScenarioEventConditionValidationException(
                    "PROBABILITY condition requires `probability` field"
                )
            if not (0.0 <= self.probability <= 1.0):
                raise ScenarioEventConditionValidationException(
                    f"probability must be in [0.0, 1.0], got {self.probability}"
                )

    @property
    def is_composite(self) -> bool:
        return self.condition_type in COMPOSITE_CONDITION_TYPES
