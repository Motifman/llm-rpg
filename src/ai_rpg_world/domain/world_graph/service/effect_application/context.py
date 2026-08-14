from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Set

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
    flags: Set[str]
    grant: List[ItemSpecId] = field(default_factory=list)
    remove: List[ItemSpecId] = field(default_factory=list)
    target_grant: List[ItemSpecId] = field(default_factory=list)
    target_remove: List[ItemSpecId] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    damage_specs: List[DamageSpec] = field(default_factory=list)
    target_damage_specs: List[DamageSpec] = field(default_factory=list)
    status_effect_specs: List[StatusEffectSpec] = field(default_factory=list)
    teleport_specs: List[TeleportSpec] = field(default_factory=list)
    atmosphere_update_specs: List[AtmosphereUpdateSpec] = field(default_factory=list)
    create_connection_specs: List[CreateConnectionSpec] = field(default_factory=list)
    destroy_connection_specs: List[DestroyConnectionSpec] = field(default_factory=list)
    satisfy_need_specs: List[SatisfyNeedSpec] = field(default_factory=list)
    passage_specs: List[PassageStateUpdateSpec] = field(default_factory=list)
    meeting_calls: List[str] = field(default_factory=list)
    room_occupancy_display_specs: List[RoomOccupancyDisplaySpec] = field(
        default_factory=list
    )
    summaries: List[AppliedEffectSummary] = field(default_factory=list)
    current_tick: Optional[WorldTick] = None
    acting_item_aggregate: Optional[ItemAggregate] = None
    target_item_aggregate: Optional[ItemAggregate] = None
    acting_player_status: Optional[PlayerStatusAggregate] = None
    target_player_status: Optional[PlayerStatusAggregate] = None
    interaction_parameters: Optional[dict] = None
    acting_player_display_name: Optional[str] = None
    owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None
    loot_table_repository: Optional[LootTableRepository] = None

    def replace_object(self, updated: SpotObject) -> None:
        """interior を差し替え、acting_object と同じ id なら同期する。"""
        self.interior = self.interior.replace_object(updated)
        if (
            self.acting_object is not None
            and updated.object_id == self.acting_object.object_id
        ):
            self.acting_object = updated
