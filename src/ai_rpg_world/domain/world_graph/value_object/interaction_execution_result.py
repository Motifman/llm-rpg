from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple

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
class InteractionExecutionResult:
    """インタラクション適用後のスナップショット（ドメインサービスが返す）"""

    new_interior: SpotInterior
    new_flags: FrozenSet[str]
    messages: Tuple[str, ...]
    action_display_label: str
    item_spec_ids_to_grant: Tuple[ItemSpecId, ...]
    item_spec_ids_to_remove: Tuple[ItemSpecId, ...]
    # クロスドメイン効果（WorldGraphEffectResult から伝播）
    damage_specs: Tuple[DamageSpec, ...] = ()
    status_effect_specs: Tuple[StatusEffectSpec, ...] = ()
    teleport_specs: Tuple[TeleportSpec, ...] = ()
    # CALL_MEETING が発火した回数ぶんの trigger 名。application 層が
    # 実際の招集を行う (誰を集めるか / フェーズ遷移は domain の外)。
    meeting_call_triggers: Tuple[str, ...] = ()
    room_occupancy_display_specs: Tuple[RoomOccupancyDisplaySpec, ...] = ()
    atmosphere_update_specs: Tuple[AtmosphereUpdateSpec, ...] = ()
    create_connection_specs: Tuple[CreateConnectionSpec, ...] = ()
    destroy_connection_specs: Tuple[DestroyConnectionSpec, ...] = ()
    satisfy_need_specs: Tuple[SatisfyNeedSpec, ...] = ()
    deposit_gold_specs: Tuple[DepositGoldSpec, ...] = ()
    passage_state_updates: Tuple[PassageStateUpdateSpec, ...] = ()
    # Phase 4-A: acting item instance の state が変更されたか。True のとき
    # caller (SpotInteractionApplicationService 等) は item_aggregate を save する。
    item_instance_state_changed: bool = False
    # Phase 4-B: target item instance (cross-instance interaction の作用先) の
    # state が変更されたか。caller が target_item_aggregate を save するのに使う。
    target_item_instance_state_changed: bool = False
    # Phase 4-D-2: 行動者プレイヤーの自由 state が変更されたか。
    # True のとき caller (アプリ層) が player_status_repository.save() する。
    acting_player_state_changed: bool = False
    # Phase 4-E: 行為者本人にツール結果として返す直接効果サマリ。
    # 行為者は自分の行動の直接結果をここから読み取り、観測ストリームには
    # 流れない（二重観測を防ぐため）。
    direct_effects: Tuple[AppliedEffectSummary, ...] = ()
    # Phase 4-E: 同スポットの第三者へ観測として配信される副次効果サマリ。
    # アプリ層が観測ディスパッチに渡す。行為者本人は受信側から除外される。
    public_observable_effects: Tuple[AppliedEffectSummary, ...] = ()
    # trace 転記用。エージェントには出さない (プロンプトの現在状態のみ)。
    hidden_effects: Tuple[AppliedEffectSummary, ...] = ()
