from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class DesignLocation:
    declaration: str
    name: str
    field: str

    def __str__(self) -> str:
        return f"{self.declaration} {self.name!r} {self.field}"
