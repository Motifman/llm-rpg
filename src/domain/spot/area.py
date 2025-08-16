from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.spot.spot import Spot


@dataclass(frozen=True)
class Area:
    area_id: int
    name: str
    description: str