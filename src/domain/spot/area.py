from dataclasses import dataclass
from typing import List
from src.domain.spot.spot import Spot


@dataclass(frozen=True)
class Area:
    area_id: int
    name: str
    description: str