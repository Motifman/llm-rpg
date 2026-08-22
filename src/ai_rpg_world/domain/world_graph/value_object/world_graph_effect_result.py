from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
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
    DepositGoldSpec,
    SatisfyNeedSpec,
    StatusEffectSpec,
    TeleportSpec,
)


@dataclass(frozen=True)
class ItemRemovalRequirements:
    """効果適用前に検証できる、行為者・対象者別の品目削除要求。"""

    actor_item_spec_ids: Tuple[ItemSpecId, ...] = ()
    target_item_spec_ids: Tuple[ItemSpecId, ...] = ()


@dataclass(frozen=True)
class WorldGraphEffectResult:
    """WorldGraph effects 適用後の結果スナップショット。"""

    new_interior: SpotInterior
    updated_object_id: Optional[int]
    new_flags: FrozenSet[str]
    messages: Tuple[str, ...]
    item_spec_ids_to_grant: Tuple[ItemSpecId, ...]
    item_spec_ids_to_remove: Tuple[ItemSpecId, ...]
    # 対人 interaction で「対象プレイヤーの持ち物」に対して適用する分。
    # 行為者ぶんと同じバケットに混ぜてはいけない。奪う (take) は「対象から
    # REMOVE_ITEM、行為者に GIVE_ITEM」の 2 効果で書くので、混ざると自分から
    # 自分へ移す no-op になり、しかも成功として返る (静かな失敗)。
    target_item_spec_ids_to_grant: Tuple[ItemSpecId, ...] = ()
    target_item_spec_ids_to_remove: Tuple[ItemSpecId, ...] = ()
    # クロスドメイン効果（application 層が combat/player ドメインへ適用する）
    damage_specs: Tuple[DamageSpec, ...] = ()
    # 対人 interaction で「対象プレイヤー」に適用するダメージ。行為者ぶんと
    # 混ぜてはいけない。混ぜると「相手を刺したつもりが自分が傷ついた」という、
    # 成功として返る誤動作になる。
    target_damage_specs: Tuple[DamageSpec, ...] = ()
    status_effect_specs: Tuple[StatusEffectSpec, ...] = ()
    teleport_specs: Tuple[TeleportSpec, ...] = ()
    atmosphere_update_specs: Tuple[AtmosphereUpdateSpec, ...] = ()
    create_connection_specs: Tuple[CreateConnectionSpec, ...] = ()
    destroy_connection_specs: Tuple[DestroyConnectionSpec, ...] = ()
    satisfy_need_specs: Tuple[SatisfyNeedSpec, ...] = ()
    deposit_gold_specs: Tuple[DepositGoldSpec, ...] = ()
    passage_state_updates: Tuple[PassageStateUpdateSpec, ...] = ()
    # CALL_MEETING が発火した回数ぶんの trigger 名。application 層が
    # これを見て招集する。domain 側は「押された」以上のことを知らない。
    meeting_call_triggers: Tuple[str, ...] = ()
    room_occupancy_display_specs: Tuple[RoomOccupancyDisplaySpec, ...] = ()
    # Phase 4-A: acting item instance に対して state 変更が起きたかどうか。
    # True なら caller (app service) が item_aggregate を save する責務を持つ。
    # acting_item_aggregate を渡さなかった呼び出しでは常に False。
    item_instance_state_changed: bool = False
    # Phase 4-B: target item instance (cross-instance interaction の作用先)
    # に対して state 変更が起きたかどうか。same semantics as acting 版。
    target_item_instance_state_changed: bool = False
    # Phase 4-D-2: 行動者プレイヤーの自由 state に変更が起きたかどうか。
    # True なら caller (app service) が player_status_repository.save() する。
    acting_player_state_changed: bool = False
    # Phase 4-E: visibility 別の効果サマリ。
    # actor_direct: 行為者のツール結果に返す
    # public_observable: 同スポットの第三者に観測イベントとして配信
    # hidden: ツール結果にも観測にも露出させない（本人プロンプトの現在状態のみ）
    actor_direct_effects: Tuple[AppliedEffectSummary, ...] = ()
    public_observable_effects: Tuple[AppliedEffectSummary, ...] = ()
    hidden_effects: Tuple[AppliedEffectSummary, ...] = ()
