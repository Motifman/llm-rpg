"""BeingAttachment 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingAttachmentValidationException,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class TestBeingAttachmentValidation:
    """BeingAttachment のバリデーション挙動。"""

    def test_有効な_WorldId_と_PlayerId_で生成できる(self) -> None:
        """正しい型の引数でインスタンス化される。"""
        attachment = BeingAttachment(
            world_id=WorldId(1), player_id=PlayerId(2)
        )
        assert attachment.world_id == WorldId(1)
        assert attachment.player_id == PlayerId(2)

    def test_world_id_が_WorldId_でないと_ValidationException_を投げる(self) -> None:
        """world_id が VO でなければドメイン例外。"""
        with pytest.raises(BeingAttachmentValidationException, match="world_id"):
            BeingAttachment(world_id=1, player_id=PlayerId(2))  # type: ignore[arg-type]

    def test_player_id_が_PlayerId_でないと_ValidationException_を投げる(self) -> None:
        """player_id が VO でなければドメイン例外。"""
        with pytest.raises(BeingAttachmentValidationException, match="player_id"):
            BeingAttachment(world_id=WorldId(1), player_id=2)  # type: ignore[arg-type]


class TestBeingAttachmentEquality:
    """BeingAttachment の等価性挙動 (frozen dataclass)。"""

    def test_同じ_world_と_player_なら等しい(self) -> None:
        """両フィールド同値なら ``==`` が True。"""
        a = BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        b = BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        assert a == b

    def test_world_が違うと等しくない(self) -> None:
        """world_id が違えば等しくない。"""
        a = BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        b = BeingAttachment(world_id=WorldId(99), player_id=PlayerId(2))
        assert a != b

    def test_hashable(self) -> None:
        """frozen dataclass なので set / dict キーとして使える。"""
        a = BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        b = BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2))
        assert len({a, b}) == 1
