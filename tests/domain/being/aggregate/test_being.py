"""Being 集約ルートの構成・不変条件・attach/detach 挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingAlreadyAttachedException,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


def _attachment(world: int = 1, player: int = 2) -> BeingAttachment:
    return BeingAttachment(world_id=WorldId(world), player_id=PlayerId(player))


class TestBeingConstruction:
    """Being 集約のコンストラクタ挙動。"""

    def test_BeingId_と_Identity_を渡すと生成できる(self) -> None:
        """attachment を省略すれば未 attach 状態で生成される。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.being_id == BeingId("ada")
        assert being.identity == _identity()
        assert being.attachment is None
        assert being.is_attached is False

    def test_attachment_を渡して生成できる(self) -> None:
        """初期から attachment 付きで生成できる。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(),
        )
        assert being.attachment == _attachment()
        assert being.is_attached is True

    def test_being_id_が_BeingId_でないと_TypeError_を投げる(self) -> None:
        """being_id が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            Being(being_id="ada", identity=_identity())  # type: ignore[arg-type]

    def test_identity_が_BeingIdentity_でないと_TypeError_を投げる(self) -> None:
        """identity が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="identity"):
            Being(being_id=BeingId("ada"), identity="アダ")  # type: ignore[arg-type]

    def test_attachment_が_BeingAttachment_でないと_TypeError_を投げる(self) -> None:
        """attachment が VO でも None でもなければ TypeError。"""
        with pytest.raises(TypeError, match="attachment"):
            Being(
                being_id=BeingId("ada"),
                identity=_identity(),
                attachment="not-a-vo",  # type: ignore[arg-type]
            )

    def test_初期状態では_events_が空(self) -> None:
        """AggregateRoot 由来の event リストは初期空。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.get_events() == []


class TestBeingAttachDetach:
    """Being.attach / detach の挙動。"""

    def test_未_attach_から_attach_すると_attachment_が更新される(self) -> None:
        """attach 後に attachment と is_attached が更新される。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        being.attach(_attachment())
        assert being.attachment == _attachment()
        assert being.is_attached is True

    def test_既に_attach_済みで_attach_を呼ぶと_例外を投げる(self) -> None:
        """0..1 制約: 多重 attach は BeingAlreadyAttachedException。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(world=1),
        )
        with pytest.raises(BeingAlreadyAttachedException):
            being.attach(_attachment(world=2))

    def test_attach_の引数が_VO_でないと_TypeError_を投げる(self) -> None:
        """型違反は TypeError で弾く (BusinessRuleException ではない)。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        with pytest.raises(TypeError):
            being.attach("not-a-vo")  # type: ignore[arg-type]

    def test_detach_すると_attachment_が_None_に戻る(self) -> None:
        """detach 後は未 attach 状態。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(),
        )
        being.detach()
        assert being.attachment is None
        assert being.is_attached is False

    def test_detach_は解除前の値を返す(self) -> None:
        """detach の戻り値で解除前 attachment を取得できる。"""
        attachment = _attachment()
        being = Being(
            being_id=BeingId("ada"), identity=_identity(), attachment=attachment
        )
        assert being.detach() == attachment

    def test_未_attach_で_detach_すると_None_を返す_例外は出ない(self) -> None:
        """未 attach での detach は no-op として None を返す。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.detach() is None

    def test_detach_して_attach_し直せる(self) -> None:
        """乗り換えシナリオ: detach → attach の往復で別世界に乗せ替えられる。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(world=1),
        )
        previous = being.detach()
        assert previous == _attachment(world=1)
        being.attach(_attachment(world=2))
        assert being.attachment == _attachment(world=2)
