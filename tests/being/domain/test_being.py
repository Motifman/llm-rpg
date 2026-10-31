"""Being 集約が、人柄と所属を持ち、所属を付け外ししても ID と人柄を保つことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingAlreadyAttachedException,
    BeingNotAttachedException,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


def _persona() -> Persona:
    return Persona(name="アダ", first_person="わたし")


def _attachment(world: int = 1, player: int = 2) -> BeingAttachment:
    return BeingAttachment(world_id=world, player_id=player)


class TestBeingConstruction:
    """Being 集約のコンストラクタ挙動。"""

    def test_being_without_attachment_is_detached(self) -> None:
        """attachment を省略すれば未 attach 状態で生成される。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())
        assert being.being_id == BeingId("ada")
        assert being.persona == _persona()
        assert being.attachment is None
        assert being.is_attached is False

    def test_attachment_can_create(self) -> None:
        """初期から attachment 付きで生成できる。"""
        being = Being(
            being_id=BeingId("ada"),
            persona=_persona(),
            attachment=_attachment(),
        )
        assert being.attachment == _attachment()
        assert being.is_attached is True

    def test_being_id_being_id_raises_type_error(self) -> None:
        """being_id が VO でなければ TypeError。"""
        with pytest.raises(TypeError, match="being_id"):
            Being(being_id="ada", persona=_persona())  # type: ignore[arg-type]

    def test_non_persona_raises_type_error(self) -> None:
        """persona が Persona でなければ TypeError を投げる。"""
        with pytest.raises(TypeError, match="persona"):
            Being(being_id=BeingId("ada"), persona="アダ")  # type: ignore[arg-type]

    def test_attachment_being_attachment_raises_type_error(self) -> None:
        """attachment が VO でも None でもなければ TypeError。"""
        with pytest.raises(TypeError, match="attachment"):
            Being(
                being_id=BeingId("ada"),
                persona=_persona(),
                attachment="not-a-vo",  # type: ignore[arg-type]
            )

    def test_initial_state_has_no_events(self) -> None:
        """AggregateRoot 由来の event リストは初期空。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())
        assert being.get_events() == []


class TestBeingAttachDetach:
    """Being.attach / detach の挙動。"""

    def test_attach_attachment_updated(self) -> None:
        """attach 後に attachment と is_attached が更新される。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())
        being.attach(_attachment())
        assert being.attachment == _attachment()
        assert being.is_attached is True

    @pytest.mark.parametrize("world, player", [(1, 2), (2, 2), (2, 99)])
    def test_attach_raises_exception(self, world: int, player: int) -> None:
        """接続済みなら同じ対・別の対への接続を拒否し、元の接続を保持する。"""
        previous = _attachment(world=1, player=2)
        being = Being(being_id=BeingId("ada"), persona=_persona(), attachment=previous)
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
        being = Being(being_id=BeingId("ada"), persona=_persona(), attachment=previous)
        assert being.attachment == previous
        assert being.is_attached is initially_attached

        with pytest.raises(TypeError, match="attachment"):
            being.attach("not-a-vo")  # type: ignore[arg-type]

        assert being.attachment == previous
        assert being.is_attached is initially_attached

    def test_detach_clears_attachment(self) -> None:
        """入っている Being を外すと、所属が無くなり、未接続になる。"""
        being = Being(being_id=BeingId("ada"), persona=_persona(), attachment=_attachment())

        being.detach()

        assert being.attachment is None
        assert being.is_attached is False

    def test_detach_when_not_attached_raises(self) -> None:
        """どこにも入っていない Being を外そうとすると、BeingNotAttachedException で断り、未接続のまま。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())

        with pytest.raises(BeingNotAttachedException):
            being.detach()

        assert being.attachment is None

    @pytest.mark.parametrize("world, player", [(2, 2), (2, 99)])
    def test_switching_attachments_preserves_id_and_persona(self, world: int, player: int) -> None:
        """世界だけ替える場合も身体も替える場合も、解除中と接続後に ID と人柄が残る。"""
        being_id = BeingId("ada")
        persona = Persona(name="アダ", first_person="わたし", traits=("慎重",))
        previous = _attachment(world=1, player=2)
        destination = _attachment(world=world, player=player)
        being = Being(being_id=being_id, persona=persona, attachment=previous)

        being.detach()
        assert being.attachment is None
        assert being.is_attached is False
        assert being.being_id == being_id
        assert being.persona == persona

        being.attach(destination)
        assert being.attachment == destination
        assert being.is_attached is True
        assert being.being_id == being_id
        assert being.persona == persona


class TestBeingMoveTo:
    """Being.move_to が、入っているかどうかを外に聞かせずに、所属を移すことを保証する。"""

    @pytest.mark.parametrize("world, player", [(1, 2), (2, 2), (2, 99)])
    def test_attached_being_moves_to_the_new_attachment(self, world: int, player: int) -> None:
        """入っている Being は、同じ所属も別の所属も、外してから新しい所属に入る。ID と人柄は変わらない。"""
        persona = _persona()
        being = Being(being_id=BeingId("ada"), persona=persona, attachment=_attachment(world=1, player=2))

        being.move_to(_attachment(world=world, player=player))

        assert being.attachment == _attachment(world=world, player=player)
        assert (being.being_id, being.persona) == (BeingId("ada"), persona)

    def test_detached_being_simply_attaches(self) -> None:
        """どこにも入っていない Being は、そのまま新しい所属に入る。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())

        being.move_to(_attachment())

        assert being.attachment == _attachment()

    @pytest.mark.parametrize("initially_attached", [False, True])
    def test_non_attachment_raises_and_keeps_the_attachment(self, initially_attached: bool) -> None:
        """所属でない値を渡すと TypeError で断り、元の所属を変えない。"""
        previous = _attachment() if initially_attached else None
        being = Being(being_id=BeingId("ada"), persona=_persona(), attachment=previous)

        with pytest.raises(TypeError, match="attachment"):
            being.move_to("not-a-vo")  # type: ignore[arg-type]

        assert being.attachment == previous
