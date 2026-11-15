from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone
from ai_rpg_world.game_world.application.action.hold_item import HoldItem, HoldItemCommand
from ai_rpg_world.game_world.application.action.put_away_item import PutAwayItem, PutAwayItemCommand
from ai_rpg_world.game_world.domain.action.built_in_attempts import HoldItemAttempt, PutAwayItemAttempt
from tests.game_world.application.action.world_for_item_actions import ALICE, PICKAXE, ROPE, WorldForItemActions


class TestHoldAndPutAwayItem:
    """HoldItem と PutAwayItem が、行う人の荷と手のあいだで品物を移すことを保証する。"""

    def test_held_item_moves_from_pack_into_hands(self) -> None:
        """荷にしまった縄を手に持つと ActionDone が返り、縄は手に移り、持ち物からは消えない。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id,))
        [rope] = world.carried_by(ALICE)

        reply = HoldItem(world.carry_out)(HoldItemCommand(HoldItemAttempt(ALICE, rope)))

        assert reply == ActionDone()
        assert world.held_by(ALICE) == (rope,)
        assert world.carried_by(ALICE) == (rope,)

    def test_holding_two_handed_item_puts_away_what_hands_held(self) -> None:
        """縄を手に持っているときに両手のつるはしを持つと、縄は荷に戻り、手にはつるはしだけがある。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id, PICKAXE.item_spec_id))
        rope, pickaxe = world.carried_by(ALICE)
        HoldItem(world.carry_out)(HoldItemCommand(HoldItemAttempt(ALICE, rope)))
        world.pass_ticks(1)

        HoldItem(world.carry_out)(HoldItemCommand(HoldItemAttempt(ALICE, pickaxe)))

        assert world.held_by(ALICE) == (pickaxe,)
        assert set(world.carried_by(ALICE)) == {rope, pickaxe}

    def test_put_away_item_moves_from_hands_into_pack(self) -> None:
        """手に持った縄をしまうと ActionDone が返り、縄は手から離れ、荷に残る。"""
        world = WorldForItemActions(alice_carries=(ROPE.item_spec_id,))
        [rope] = world.carried_by(ALICE)
        HoldItem(world.carry_out)(HoldItemCommand(HoldItemAttempt(ALICE, rope)))
        world.pass_ticks(1)

        reply = PutAwayItem(world.carry_out)(PutAwayItemCommand(PutAwayItemAttempt(ALICE, rope)))

        assert reply == ActionDone()
        assert world.held_by(ALICE) == ()
        assert world.carried_by(ALICE) == (rope,)
