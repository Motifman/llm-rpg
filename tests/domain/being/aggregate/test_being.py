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

    def test_being_id_identity_can_create(self) -> None:
        """attachment を省略すれば未 attach 状態で生成される。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.being_id == BeingId("ada")
        assert being.identity == _identity()
        assert being.attachment is None
        assert being.is_attached is False

    def test_attachment_can_create(self) -> None:
        """初期から attachment 付きで生成できる。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(),
        )
        assert being.attachment == _attachment()
        assert being.is_attached is True

    def test_being_id_being_id_raises_type_error(self) -> None:
        """being_id が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            Being(being_id="ada", identity=_identity())  # type: ignore[arg-type]

    def test_id_entity_being_id_entity_raises_type_error(self) -> None:
        """identity が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="identity"):
            Being(being_id=BeingId("ada"), identity="アダ")  # type: ignore[arg-type]

    def test_attachment_being_attachment_raises_type_error(self) -> None:
        """attachment が VO でも None でもなければ TypeError。"""
        with pytest.raises(TypeError, match="attachment"):
            Being(
                being_id=BeingId("ada"),
                identity=_identity(),
                attachment="not-a-vo",  # type: ignore[arg-type]
            )

    def test_initial_state_has_no_events(self) -> None:
        """AggregateRoot 由来の event リストは初期空。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.get_events() == []


class TestBeingAttachDetach:
    """Being.attach / detach の挙動。"""

    def test_attach_attachment_updated(self) -> None:
        """attach 後に attachment と is_attached が更新される。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        being.attach(_attachment())
        assert being.attachment == _attachment()
        assert being.is_attached is True

    @pytest.mark.parametrize("world, player", [(1, 2), (2, 2), (2, 99)])
    def test_attach_raises_exception(self, world: int, player: int) -> None:
        """接続済みなら同じ対・別の対への接続を拒否し、元の接続を保持する。"""
        previous = _attachment(world=1, player=2)
        being = Being(being_id=BeingId("ada"), identity=_identity(), attachment=previous)
        assert being.attachment == previous
        assert being.is_attached is True

        with pytest.raises(BeingAlreadyAttachedException):
            being.attach(_attachment(world=world, player=player))

        assert being.attachment == previous
        assert being.is_attached is True

    @pytest.mark.parametrize("initially_attached", [False, True])
    def test_attach_vo_raises_type_error(self, initially_attached: bool) -> None:
        """接続の型違反を拒否しても、未接続・既接続いずれの元状態も変えない。"""
        previous = _attachment() if initially_attached else None
        being = Being(being_id=BeingId("ada"), identity=_identity(), attachment=previous)
        assert being.attachment == previous
        assert being.is_attached is initially_attached

        with pytest.raises(TypeError, match="attachment"):
            being.attach("not-a-vo")  # type: ignore[arg-type]

        assert being.attachment == previous
        assert being.is_attached is initially_attached

    def test_detach_returns_previous_attachment_and_clears_state(self) -> None:
        """解除は直前の世界・プレイヤー対を返し、主体を未接続にする。"""
        previous = _attachment()
        being = Being(being_id=BeingId("ada"), identity=_identity(), attachment=previous)

        assert being.detach() == previous
        assert being.attachment is None
        assert being.is_attached is False

    def test_attach_detach_none_raises_exception(self) -> None:
        """未 attach での detach は no-op として None を返す。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.detach() is None

    @pytest.mark.parametrize("world, player", [(2, 2), (2, 99)])
    def test_switching_attachments_preserves_identity_and_declarations(self, world: int, player: int) -> None:
        """世界だけ替える場合も身体も替える場合も、解除中と接続後に主体情報が残る。"""
        being_id = BeingId("ada")
        identity = _identity()
        kinds = frozenset({MemoryKind.EPISODIC, MemoryKind.MEMO})
        previous = _attachment(world=1, player=2)
        destination = _attachment(world=world, player=player)
        being = Being(
            being_id=being_id,
            identity=identity,
            attachment=previous,
            declared_memory_kinds=kinds,
        )

        assert being.detach() == previous
        assert being.attachment is None
        assert being.is_attached is False
        assert being.being_id == being_id
        assert being.identity == identity
        assert being.declared_memory_kinds == kinds

        being.attach(destination)
        assert being.attachment == destination
        assert being.is_attached is True
        assert being.being_id == being_id
        assert being.identity == identity
        assert being.declared_memory_kinds == kinds


class TestBeingDeclaredMemoryKinds:
    """Being.declared_memory_kinds の宣言挙動。"""

    def test_omitted_attachments_default_to_empty_set(self) -> None:
        """declared_memory_kinds を省略すれば空 frozenset。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        assert being.declared_memory_kinds == frozenset()
        assert being.declares(MemoryKind.MEMO) is False

    def test_declared_memory_kinds_are_isolated_from_caller_updates(self) -> None:
        """宣言の所属は入力どおりで、入力や取得集合への外側の更新が主体へ波及しない。"""
        source = [MemoryKind.EPISODIC, MemoryKind.MEMO]
        expected = frozenset({MemoryKind.EPISODIC, MemoryKind.MEMO})
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=source,
        )
        assert being.declared_memory_kinds == expected
        assert being.declares(MemoryKind.EPISODIC) is True
        assert being.declares(MemoryKind.MEMO) is True
        assert being.declares(MemoryKind.SEMANTIC) is False

        source.clear()
        assert being.declared_memory_kinds == expected
        exposed = being.declared_memory_kinds
        exposed |= {MemoryKind.SEMANTIC}
        assert being.declared_memory_kinds == expected
        assert being.declares(MemoryKind.SEMANTIC) is False

    def test_duplicate_kind_frozenset(self) -> None:
        """同じ kind を 2 回渡しても集合化される。"""
        being = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=[MemoryKind.MEMO, MemoryKind.MEMO],
        )
        assert being.declared_memory_kinds == frozenset({MemoryKind.MEMO})

    def test_memory_kind_raises_type_error(self) -> None:
        """型違反は TypeError として弾く。"""
        with pytest.raises(TypeError, match="MemoryKind"):
            Being(
                being_id=BeingId("ada"),
                identity=_identity(),
                declared_memory_kinds=["memo"],  # type: ignore[list-item]
            )

    def test_declared_memory_kinds_being(self) -> None:
        """宣言差し替えは副作用なし: 元 Being の宣言は変わらず、新 Being に反映。"""
        original = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            declared_memory_kinds=[MemoryKind.EPISODIC],
        )
        updated = original.with_declared_memory_kinds([MemoryKind.EPISODIC, MemoryKind.SEMANTIC])
        assert original.declared_memory_kinds == frozenset({MemoryKind.EPISODIC})
        assert updated.declared_memory_kinds == frozenset({MemoryKind.EPISODIC, MemoryKind.SEMANTIC})
        assert updated.being_id == original.being_id
        assert updated.identity == original.identity

    def test_declared_memory_kinds_attachment(self) -> None:
        """宣言差し替え時に既存 attachment はそのまま新 Being に複製される。"""
        original = Being(
            being_id=BeingId("ada"),
            identity=_identity(),
            attachment=_attachment(),
            declared_memory_kinds=[MemoryKind.MEMO],
        )
        updated = original.with_declared_memory_kinds([MemoryKind.MEMO, MemoryKind.SEMANTIC])
        assert updated.attachment == _attachment()
