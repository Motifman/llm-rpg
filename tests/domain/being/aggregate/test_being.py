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
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
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


class TestBeingDeclaredMemoryKinds:
    """Being.declared_memory_kinds の宣言挙動。"""

    def test_省略時は空集合(self) -> None:
        """declared_memory_kinds を省略すれば空 frozenset。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.declared_memory_kinds == frozenset()
        assert being.declares(MemoryKind.MEMO) is False

    def test_宣言した_kind_が_declares_で_True_になる(self) -> None:
        """渡した kind は declared_memory_kinds に含まれ declares が True。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=[MemoryKind.EPISODIC, MemoryKind.MEMO],
        )
        assert being.declared_memory_kinds == frozenset(
            {MemoryKind.EPISODIC, MemoryKind.MEMO}
        )
        assert being.declares(MemoryKind.EPISODIC) is True
        assert being.declares(MemoryKind.MEMO) is True
        assert being.declares(MemoryKind.SEMANTIC) is False

    def test_重複した_kind_は_frozenset_で吸収される(self) -> None:
        """同じ kind を 2 回渡しても集合化される。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=[MemoryKind.MEMO, MemoryKind.MEMO],
        )
        assert being.declared_memory_kinds == frozenset({MemoryKind.MEMO})

    def test_非_MemoryKind_要素を渡すと_TypeError(self) -> None:
        """型違反は TypeError として弾く。"""
        with pytest.raises(TypeError, match="MemoryKind"):
            Being(
                being_id=BeingId("ada"),
                identity=_identity(),
                declared_memory_kinds=["memo"],  # type: ignore[list-item]
            )

    def test_with_declared_memory_kinds_は新しい_Being_を返し元は不変(self) -> None:
        """宣言差し替えは副作用なし: 元 Being の宣言は変わらず、新 Being に反映。"""
        original = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=[MemoryKind.EPISODIC],
        )
        updated = original.with_declared_memory_kinds(
            [MemoryKind.EPISODIC, MemoryKind.SEMANTIC]
        )
        assert original.declared_memory_kinds == frozenset({MemoryKind.EPISODIC})
        assert updated.declared_memory_kinds == frozenset(
            {MemoryKind.EPISODIC, MemoryKind.SEMANTIC}
        )
        assert updated.being_id == original.being_id
        assert updated.identity == original.identity

    def test_with_declared_memory_kinds_は_attachment_を引き継ぐ(self) -> None:
        """宣言差し替え時に既存 attachment はそのまま新 Being に複製される。"""
        original = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(),
            declared_memory_kinds=[MemoryKind.MEMO],
        )
        updated = original.with_declared_memory_kinds([MemoryKind.MEMO, MemoryKind.SEMANTIC])
        assert updated.attachment == _attachment()
