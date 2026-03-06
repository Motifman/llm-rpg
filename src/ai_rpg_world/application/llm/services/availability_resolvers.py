"""ツール利用可否リゾルバのデフォルト実装"""

from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


class NoOpAvailabilityResolver(IAvailabilityResolver):
    """何もしないツールは常に利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        return True


class SetDestinationAvailabilityResolver(IAvailabilityResolver):
    """目的地設定ツールは、現在地があり利用可能な移動先が1件以上あるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        if context.current_spot_id is None:
            return False
        if context.available_moves is None or context.total_available_moves is None:
            return False
        return context.total_available_moves > 0


class WhisperAvailabilityResolver(IAvailabilityResolver):
    """囁きツールは、視界内に自分以外のプレイヤーがいるときに利用可能。"""

    def is_available(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> bool:
        if context is None:
            return False
        return any(
            obj.object_kind == "player" and not obj.is_self
            for obj in context.visible_objects
        )
