"""取り出した Being 列から、同一 (world, player) への付着が 0..1 かを判定する。"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingMultipleAttachmentException,
)


def unique_attached_being(matches: Sequence[Being]) -> Being | None:
    """既に取り出した Being の列から、一意な 1 件を返す。

    - 0 件: None
    - 1 件: その Being
    - 2 件以上: BeingMultipleAttachmentException
    """
    if not matches:
        return None
    if len(matches) > 1:
        raise BeingMultipleAttachmentException(
            f"multiple Beings attached: {[b.being_id.value for b in matches]}"
        )
    return matches[0]


__all__ = ["unique_attached_being"]
