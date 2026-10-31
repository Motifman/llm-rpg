"""Being がいま、どの世界のどのプレイヤーとして入っているか。

番号はゲームの型 (``WorldId``、``PlayerId``) にせず、正の int で持つ。Being はゲームのパッケージを import しない
ため。ゲームの型との変換はゲームの側で行う (design_decisions D1469-4)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import BeingAttachmentValidationException


def _require_positive_int(field_name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BeingAttachmentValidationException(f"BeingAttachment.{field_name} must be positive int, got {value!r}")


@dataclass(frozen=True)
class BeingAttachment:
    """同時に入れる環境は 1 つまで (``Being.attach``)。離れても経験は Being に残る。"""

    world_id: int
    player_id: int

    def __post_init__(self) -> None:
        _require_positive_int("world_id", self.world_id)
        _require_positive_int("player_id", self.player_id)


__all__ = ["BeingAttachment"]
