from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    AtmosphereUpdateSpec,
    CreateConnectionSpec,
    DamageSpec,
    DepositGoldSpec,
    DestroyConnectionSpec,
    PassageStateUpdateSpec,
    RoomOccupancyDisplaySpec,
    SatisfyNeedSpec,
    StatusEffectSpec,
    TeleportSpec,
)


@dataclass
class EffectApplicationState:
    """apply_effects ループ中の mutable 状態。各 handler が in-place で更新する。"""

    interior: SpotInterior
    acting_object: SpotObject | None
    flags: set[str]
    grant: list[ItemSpecId] = field(default_factory=list)
    remove: list[ItemSpecId] = field(default_factory=list)
    target_grant: list[ItemSpecId] = field(default_factory=list)
    target_remove: list[ItemSpecId] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    damage_specs: list[DamageSpec] = field(default_factory=list)
    target_damage_specs: list[DamageSpec] = field(default_factory=list)
    status_effect_specs: list[StatusEffectSpec] = field(default_factory=list)
    teleport_specs: list[TeleportSpec] = field(default_factory=list)
    atmosphere_update_specs: list[AtmosphereUpdateSpec] = field(default_factory=list)
    create_connection_specs: list[CreateConnectionSpec] = field(default_factory=list)
    destroy_connection_specs: list[DestroyConnectionSpec] = field(default_factory=list)
    satisfy_need_specs: list[SatisfyNeedSpec] = field(default_factory=list)
    deposit_gold_specs: list[DepositGoldSpec] = field(default_factory=list)
    passage_specs: list[PassageStateUpdateSpec] = field(default_factory=list)
    meeting_calls: list[str] = field(default_factory=list)
    room_occupancy_display_specs: list[RoomOccupancyDisplaySpec] = field(default_factory=list)
    summaries: list[AppliedEffectSummary] = field(default_factory=list)
    current_tick: WorldTick | None = None
    acting_item_aggregate: ItemAggregate | None = None
    target_item_aggregate: ItemAggregate | None = None
    acting_player_status: PlayerStatusAggregate | None = None
    target_player_status: PlayerStatusAggregate | None = None
    interaction_parameters: dict[str, Any] | None = None
    acting_player_display_name: str | None = None
    owned_item_spec_counts: Mapping[ItemSpecId, int] | None = None
    loot_table_repository: LootTableRepository | None = None
    loot_random_source: random.Random | None = None

    def replace_object(self, updated: SpotObject) -> None:
        """interior を差し替え、acting_object と同じ id なら同期する。"""
        self.interior = self.interior.replace_object(updated)
        if self.acting_object is not None and updated.object_id == self.acting_object.object_id:
            self.acting_object = updated
