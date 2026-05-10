"""AttackerRef 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.monster.value_object.attacker_ref import (
    AttackerKind,
    AttackerRef,
    AttackerRefValidationException,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestAttackerRefFactories:
    """`of_monster` / `of_player` のファクトリ生成挙動。"""

    def test_of_monster_で_kind_と_monster_id_が_設定される(self) -> None:
        """of_monster は kind=MONSTER と monster_id だけを持つ AttackerRef を返す。"""
        ref = AttackerRef.of_monster(MonsterId.create(101))
        assert ref.kind == AttackerKind.MONSTER
        assert ref.monster_id == MonsterId.create(101)
        assert ref.player_id is None
        assert ref.is_monster is True
        assert ref.is_player is False

    def test_of_player_で_kind_と_player_id_が_設定される(self) -> None:
        """of_player は kind=PLAYER と player_id だけを持つ AttackerRef を返す。"""
        ref = AttackerRef.of_player(PlayerId(7))
        assert ref.kind == AttackerKind.PLAYER
        assert ref.player_id == PlayerId(7)
        assert ref.monster_id is None
        assert ref.is_player is True
        assert ref.is_monster is False


class TestAttackerRefValidation:
    """discriminated union 制約のバリデーション挙動。"""

    def test_kind_MONSTER_で_monster_id_が_None_なら_例外(self) -> None:
        """kind=MONSTER 時に monster_id を渡さないと ValidationException を投げる。"""
        with pytest.raises(AttackerRefValidationException):
            AttackerRef(kind=AttackerKind.MONSTER, monster_id=None)

    def test_kind_MONSTER_で_player_id_を_設定すると_例外(self) -> None:
        """kind=MONSTER に player_id を併設すると ValidationException を投げる。"""
        with pytest.raises(AttackerRefValidationException):
            AttackerRef(
                kind=AttackerKind.MONSTER,
                monster_id=MonsterId.create(1),
                player_id=PlayerId(1),
            )

    def test_kind_PLAYER_で_player_id_が_None_なら_例外(self) -> None:
        """kind=PLAYER 時に player_id を渡さないと ValidationException を投げる。"""
        with pytest.raises(AttackerRefValidationException):
            AttackerRef(kind=AttackerKind.PLAYER, player_id=None)

    def test_kind_PLAYER_で_monster_id_を_設定すると_例外(self) -> None:
        """kind=PLAYER に monster_id を併設すると ValidationException を投げる。"""
        with pytest.raises(AttackerRefValidationException):
            AttackerRef(
                kind=AttackerKind.PLAYER,
                player_id=PlayerId(1),
                monster_id=MonsterId.create(1),
            )

    def test_frozen_dataclass_で_変更不可(self) -> None:
        """AttackerRef は frozen dataclass のためフィールド変更で例外を投げる。"""
        ref = AttackerRef.of_monster(MonsterId.create(1))
        with pytest.raises(Exception):
            ref.monster_id = MonsterId.create(2)  # type: ignore[misc]
