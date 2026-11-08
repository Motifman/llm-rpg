from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.action_exception import BlankWaitReasonException


@final
@dataclass(frozen=True)
class WaitReason:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankWaitReasonException(f"WaitReason must be non-blank, got {self.text!r}")


@final
@dataclass(frozen=True)
class NoReason:
    pass
