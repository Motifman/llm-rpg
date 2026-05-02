"""Sub-formatter 共通の名前解決・リポジトリ参照。親への依存を避けるための基盤。"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
        ISpotGraphRepository,
    )
    from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
        SoundPropagationService,
    )


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
