from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.map_exception import WorldIdValidationException


@dataclass(frozen=True)
class WorldId:
    """世界の一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise WorldIdValidationException(f"World ID must be positive: {self.value}")

    def __str__(self) -> str:
        return str(self.value)


# Phase 3 Step 3a (Issue #470): spot_graph / world_runtime 系の wiring は単一 world
# 前提で動いており、Being.attachment.world_id の暫定値として ``WorldId(1)`` を
# ハードコードしていた。本定数で一本化し、Step 6-full で実 WorldId を thread
# する際に grep で置き換え対象を集約できるようにする。
DEFAULT_SINGLE_WORLD_ID = WorldId(1)
