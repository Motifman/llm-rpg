"""観測まわりの契約（値オブジェクト・インターフェース）"""

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
    IObservationRecipientResolver,
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
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
