from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


@dataclass(frozen=True)
class ScenarioEventDef:
    """シナリオJSONで定義する自律イベント。"""

    event_id: str
    trigger: str
    once: bool
    conditions: Tuple[ScenarioEventCondition, ...]
    effects: Tuple[InteractionEffect, ...]
    observation_category: str = "environment"
    recipients: str = "all_players"
    target_spot_id: Optional[int] = None
    schedules_turn: bool = True
    breaks_movement: bool = False
    # 脱出ゲーム拡張: イベントチェーン
    # TODO: Phase 6 — ScenarioEventStageService でチェーン発火ロジックを実装する
    next_event_id: Optional[str] = None
    delay_ticks: int = 0
