"""BeingAttachment が、世界とプレイヤーの番号を正の int だけで持つことを保証する (design_decisions D1469-4)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.exception.being_exceptions import BeingAttachmentValidationException


class TestBeingAttachmentValidation:
    """BeingAttachment が受け取る番号の決まりを保証する。"""

    def test_positive_ints_are_kept(self) -> None:
        """正の int の世界とプレイヤーの番号をそのまま持つ。"""
        attachment = BeingAttachment(world_id=1, player_id=2)

        assert (attachment.world_id, attachment.player_id) == (1, 2)

    @pytest.mark.parametrize("field_name", ["world_id", "player_id"])
    @pytest.mark.parametrize("value", [0, -1, True, "1", 1.0, None])
    def test_non_positive_or_non_int_raises(self, field_name: str, value: object) -> None:
        """0 以下、bool、int でない値を渡すと BeingAttachmentValidationException を投げる。"""
        fields: dict[str, object] = {"world_id": 1, "player_id": 2, field_name: value}

        with pytest.raises(BeingAttachmentValidationException, match=field_name):
            BeingAttachment(**fields)  # type: ignore[arg-type]

    def test_game_id_type_is_rejected(self) -> None:
        """ゲームの PlayerId を渡すと BeingAttachmentValidationException を投げる。番号はゲームの側で int にしてから渡す。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        with pytest.raises(BeingAttachmentValidationException, match="player_id"):
            BeingAttachment(world_id=1, player_id=PlayerId(2))  # type: ignore[arg-type]


class TestBeingAttachmentEquality:
    """BeingAttachment の等価性を保証する。"""

    def test_same_world_and_player_are_equal_and_hash_alike(self) -> None:
        """世界とプレイヤーが同じなら等しく、set では 1 つになる。"""
        assert BeingAttachment(world_id=1, player_id=2) == BeingAttachment(world_id=1, player_id=2)
        assert len({BeingAttachment(world_id=1, player_id=2), BeingAttachment(world_id=1, player_id=2)}) == 1

    @pytest.mark.parametrize("world, player", [(99, 2), (1, 99)])
    def test_different_world_or_player_is_not_equal(self, world: int, player: int) -> None:
        """世界とプレイヤーの一方だけが違っても、等しくない。"""
        assert BeingAttachment(world_id=1, player_id=2) != BeingAttachment(world_id=world, player_id=player)
