"""観測まわりの契約（値オブジェクト・インターフェース）"""

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IWorldObjectToPlayerResolver,
    IRecipientResolutionStrategy,
    IObservationRecipientResolver,
    IObservationFormatter,
    IObservationContextBuffer,
)

__all__ = [
    "ObservationOutput",
    "ObservationEntry",
    "IWorldObjectToPlayerResolver",
    "IRecipientResolutionStrategy",
    "IObservationRecipientResolver",
    "IObservationFormatter",
    "IObservationContextBuffer",
]
