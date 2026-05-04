from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ScenarioEventCondition:
    """シナリオ自律イベントの発火条件。"""

    condition_type: str
    tick: Optional[int] = None
    tick_start: Optional[int] = None
    tick_end: Optional[int] = None
    flag_name: Optional[str] = None
    spot_id: Optional[int] = None
    object_id: Optional[int] = None
    required_state: Optional[dict[str, Any]] = None
    item_spec_id: Optional[int] = None
    # 脱出ゲーム拡張: 周期的イベント
    tick_modulo: Optional[int] = None
    tick_phase: Optional[int] = None
