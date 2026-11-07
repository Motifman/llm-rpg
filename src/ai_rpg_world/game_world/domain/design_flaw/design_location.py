from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class DesignLocation:
    declaration: str
    name: str
    field: str
