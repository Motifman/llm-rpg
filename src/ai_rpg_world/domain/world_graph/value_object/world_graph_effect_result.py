from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.cross_domain_effect_spec import (
    AtmosphereUpdateSpec,
    CreateConnectionSpec,
    DamageSpec,
    DestroyConnectionSpec,
    StatusEffectSpec,
    TeleportSpec,
)


@dataclass(frozen=True)
class WorldGraphEffectResult:
    """WorldGraph effects 適用後の結果スナップショット。"""

    new_interior: SpotInterior
    updated_object_id: Optional[int]
    new_flags: FrozenSet[str]
    messages: Tuple[str, ...]
    item_spec_ids_to_grant: Tuple[ItemSpecId, ...]
    item_spec_ids_to_remove: Tuple[ItemSpecId, ...]
    connection_passability_updates: Tuple[Tuple[ConnectionId, bool], ...]
    # クロスドメイン効果（application 層が combat/player ドメインへ適用する）
    damage_specs: Tuple[DamageSpec, ...] = ()
    status_effect_specs: Tuple[StatusEffectSpec, ...] = ()
    teleport_specs: Tuple[TeleportSpec, ...] = ()
    atmosphere_update_specs: Tuple[AtmosphereUpdateSpec, ...] = ()
    create_connection_specs: Tuple[CreateConnectionSpec, ...] = ()
    destroy_connection_specs: Tuple[DestroyConnectionSpec, ...] = ()
