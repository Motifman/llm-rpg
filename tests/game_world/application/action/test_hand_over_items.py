from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.action.hand_over_items import HandOverItems, HandOverItemsCommand
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemHandOverAttempt
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotTogether
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import InventoryFullException
from ai_rpg_world.game_world.domain.exception.person_exception import PersonNotAliveException
from tests.game_world.application.action.world_for_item_actions import (
    ALICE,
    BOB,
    CAROL,
    PICKAXE,
    ROPE,
    WorldForItemActions,
)

TWO_ITEMS = (ROPE.item_spec_id, PICKAXE.item_spec_id)


class TestHandOverItems:
    """HandOverItems が、一緒にいる相手 1 人へ品物をまとめて移し、移せなければ誰の荷も変えずに断ることを保証する。"""

    def test_handed_over_items_move_into_receivers_pack(self) -> None:
        """一緒にいる相手に縄とつるはしを渡すと ActionDone が返り、2 つとも相手の荷に移り、渡した側には残らない。"""
        world = WorldForItemActions(alice_carries=TWO_ITEMS)
        items = world.carried_by(ALICE)

        reply = HandOverItems(world.carry_out)(HandOverItemsCommand(ItemHandOverAttempt(ALICE, BOB, items, Openly())))

        assert reply == ActionDone()
        assert world.carried_by(ALICE) == ()
        assert world.carried_by(BOB) == items

    def test_person_elsewhere_cannot_be_handed_items(self) -> None:
        """別の場所にいる人に渡そうとすると共通の規則 NotTogether で断られ、品物は渡す側に残る。"""
        world = WorldForItemActions(alice_carries=TWO_ITEMS)
        items = world.carried_by(ALICE)

        reply = HandOverItems(world.carry_out)(HandOverItemsCommand(ItemHandOverAttempt(ALICE, CAROL, items, Openly())))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == NotTogether()
        assert world.carried_by(ALICE) == items
        assert world.carried_by(CAROL) == ()

    def test_receiver_without_room_for_all_refuses_and_neither_pack_changes(self) -> None:
        """荷に 1 つしか入らない相手に 2 つ渡そうとすると INVENTORY_FULL で断られ、1 つ目も移らず、渡す側の荷も変わらない。"""
        world = WorldForItemActions(alice_carries=TWO_ITEMS, bob_capacity=1)
        items = world.carried_by(ALICE)

        reply = HandOverItems(world.carry_out)(HandOverItemsCommand(ItemHandOverAttempt(ALICE, BOB, items, Openly())))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(InventoryFullException.error_code))
        assert world.carried_by(ALICE) == items
        assert world.carried_by(BOB) == ()

    def test_fallen_receiver_refuses_and_items_stay_with_giver(self) -> None:
        """倒れている人は受け取れない。倒れた相手に渡そうとすると PERSON_NOT_ALIVE で断られ、品物は渡す側に残る。"""
        world = WorldForItemActions(alice_carries=TWO_ITEMS)
        items = world.carried_by(ALICE)
        world.fell(BOB)

        reply = HandOverItems(world.carry_out)(HandOverItemsCommand(ItemHandOverAttempt(ALICE, BOB, items, Openly())))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(PersonNotAliveException.error_code))
        assert world.carried_by(ALICE) == items
        assert world.carried_by(BOB) == ()
