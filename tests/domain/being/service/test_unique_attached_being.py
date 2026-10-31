"""unique_attached_being が 0 / 1 / 2件以上をどう扱うかを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingMultipleAttachmentException,
)
from ai_rpg_world.domain.being.service.unique_attached_being import (
    unique_attached_being,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


def _persona() -> Persona:
    return Persona(name="アダ", first_person="わたし")


def _being(
    being_id: str = "ada",
    *,
    attached: tuple[int, int] | None = None,
) -> Being:
    attachment = BeingAttachment(world_id=attached[0], player_id=attached[1]) if attached is not None else None
    return Being(being_id=BeingId(being_id), persona=_persona(), attachment=attachment)


class TestUniqueAttachedBeing:
    """unique_attached_being の件数判定。"""

    def test_empty_sequence_returns_none(self) -> None:
        """空列を渡すと None を返す。"""
        assert unique_attached_being([]) is None

    def test_single_being_returns_that_being(self) -> None:
        """1 件の列を渡すとその Being を返す。"""
        being = _being("ada", attached=(1, 2))
        assert unique_attached_being([being]) is being

    @pytest.mark.parametrize("count", [2, 3])
    def test_multiple_beings_raises_exception(self, count: int) -> None:
        """同じ身体に付く主体が2件でも3件でも、一意性違反として拒否する。"""
        beings = [_being(being_id, attached=(1, 2)) for being_id in ("ada", "ben", "cal")[:count]]
        with pytest.raises(BeingMultipleAttachmentException, match="multiple Beings"):
            unique_attached_being(beings)
