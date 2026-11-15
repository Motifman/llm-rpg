from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.action.pick_up_ground_item import PickUpGroundItem, PickUpGroundItemCommand
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import GroundItemPickupAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import InventoryFullException
from tests.game_world.application.action.world_for_item_actions import ALICE, ROPE, WorldForItemActions


class TestPickUpGroundItem:
    """PickUpGroundItem が、同じ場所の地面の品物を行う人の荷へ移し、荷が満杯なら断ることを保証する。"""

    def test_picked_up_item_moves_from_ground_into_pack(self) -> None:
        """同じ場所の地面のつるはしを拾うと ActionDone が返り、つるはしは荷に入り、地面から消える。"""
        world = WorldForItemActions()
        pickaxe = world.lay_on_ground_at_camp()

        reply = PickUpGroundItem(world.carry_out)(
            PickUpGroundItemCommand(GroundItemPickupAttempt(ALICE, pickaxe, Openly()))
        )

        assert reply == ActionDone()
        assert world.carried_by(ALICE) == (pickaxe,)
        assert world.on_ground_at_camp() == ()

    def test_full_pack_refuses_and_item_stays_on_ground(self) -> None:
        """荷が満杯の人がつるはしを拾おうとすると INVENTORY_FULL で断られ、つるはしは地面に残る。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id, ROPE.item_spec_id))
        pickaxe = world.lay_on_ground_at_camp()

        reply = PickUpGroundItem(world.carry_out)(
            PickUpGroundItemCommand(GroundItemPickupAttempt(ALICE, pickaxe, Openly()))
        )

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(InventoryFullException.error_code))
        assert world.on_ground_at_camp() == (pickaxe,)
        assert pickaxe not in world.carried_by(ALICE)
