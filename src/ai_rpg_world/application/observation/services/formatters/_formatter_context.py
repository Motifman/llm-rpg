"""Sub-formatter 共通の名前解決・リポジトリ参照。親への依存を避けるための基盤。"""

from dataclasses import dataclass
from typing import Any, List, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
        ISpotGraphRepository,
    )
    from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
        SoundPropagationService,
    )


def resolve_item_spec_id_value_for_instance(
    item_repository: Optional["ItemRepository"],
    item_instance_id: ItemInstanceId,
) -> Optional[int]:
    """ItemAggregate が取れるとき item_spec_id の数値を返す。"""
    if item_repository is None:
        return None
    agg = item_repository.find_by_id(item_instance_id)
    if agg is None:
        return None
    return agg.item_spec.item_spec_id.value


def first_item_spec_id_value_from_obtained_items(
    obtained_items: List[Any],
) -> Optional[int]:
    """
    ResourceHarvestedEvent.obtained_items などから先頭の item_spec_id を int で返す。
    複数種ある場合は先頭のみ（局面 cue は 1 件に収めるため）。
    """
    for entry in obtained_items:
        if not isinstance(entry, dict):
            continue
        spec_id_raw = entry.get("item_spec_id")
        if spec_id_raw is None:
            continue
        try:
            if isinstance(spec_id_raw, int):
                return spec_id_raw
            return int(spec_id_raw)
        except (TypeError, ValueError):
            continue
    return None


@dataclass(frozen=True)
class ObservationFormatterContext:
    """
    Sub-formatter が親に依存せず名前解決・アイテム参照を行うための読み取り専用コンテキスト。
    Phase 2 以降で各 formatter がロジックを持つ際に使用する。
    """

    name_resolver: ObservationNameResolver
    item_repository: Optional["ItemRepository"]
    spot_graph_repository: Optional["ISpotGraphRepository"] = None
    sound_propagation_service: Optional["SoundPropagationService"] = None
