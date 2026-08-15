"""unique_attached_being が 0 / 1 / 2件以上をどう扱うかを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingMultipleAttachmentException,
)
from ai_rpg_world.domain.being.service.unique_attached_being import (
    unique_attached_being,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


def _being(
    being_id: str = "ada",
    *,
    attached: tuple[int, int] | None = None,
) -> Being:
    attachment = (
        BeingAttachment(world_id=WorldId(attached[0]), player_id=PlayerId(attached[1]))
        if attached is not None
        else None
    )
    return Being(
        being_id=BeingId(being_id), identity=_identity(), attachment=attachment
    )


class TestUniqueAttachedBeing:
    """unique_attached_being の件数判定。"""

    def test_empty_sequence_returns_none(self) -> None:
        """空列を渡すと None を返す。"""
        assert unique_attached_being([]) is None

    def test_single_being_returns_that_being(self) -> None:
        """1 件の列を渡すとその Being を返す。"""
        being = _being("ada", attached=(1, 2))
        assert unique_attached_being([being]) is being

    def test_multiple_beings_raises_exception(self) -> None:
        """2 件以上の列を渡すと BeingMultipleAttachmentException を投げる。"""
        ada = _being("ada", attached=(1, 2))
        ben = _being("ben", attached=(1, 2))
        with pytest.raises(
            BeingMultipleAttachmentException, match="multiple Beings"
        ):
            unique_attached_being([ada, ben])
