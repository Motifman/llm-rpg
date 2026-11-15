from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.action.drop_item import DropItem, DropItemCommand
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemDropAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import ItemNotCarriedException
from tests.game_world.application.action.world_for_item_actions import ALICE, BOB, ROPE, WorldForItemActions


class TestDropItem:
    """DropItem が、行う人の持つ品物をその場所の地面へ移し、持っていない品物は断ることを保証する。"""

    def test_dropped_item_moves_from_pack_onto_ground_where_actor_stands(self) -> None:
        """持っている縄を置くと ActionDone が返り、縄は荷から消え、行う人のいる野営地の地面に出る。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id,))
        [rope] = world.carried_by(ALICE)

        reply = DropItem(world.carry_out)(DropItemCommand(ItemDropAttempt(ALICE, rope, Openly())))

        assert reply == ActionDone()
        assert world.carried_by(ALICE) == ()
        assert world.on_ground_at_camp() == (rope,)

    def test_item_carried_by_someone_else_refuses_and_stays_with_its_owner(self) -> None:
        """他人の持つ縄を置こうとすると ITEM_NOT_CARRIED で断られ、縄は持ち主の荷に残り、地面には出ない。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id,))
        [rope] = world.carried_by(ALICE)

        reply = DropItem(world.carry_out)(DropItemCommand(ItemDropAttempt(BOB, rope, Openly())))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(ItemNotCarriedException.error_code))
        assert world.carried_by(ALICE) == (rope,)
        assert world.on_ground_at_camp() == ()
