from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration, ItemArgument
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.offered_action import OfferedItemPick, OfferedStep, OfferedValue
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Damage, DisplayName, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, item_spec, nouns, spot

_WORLD = WorldId("wording_world")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_ROPE = item_spec("rope")
_LOOT = (ArgumentDeclaration(ArgumentName("loot"), ItemArgument()),)
_LOOT_VALUE = OfferedValue("loot", "loot")


def _opened_world() -> tuple[WorldDesign, WorldSession]:
    bob = replace(character("bob", "hall"), initial_items=(_ROPE.item_spec_id,), initial_held=(_ROPE.item_spec_id,))
    design = compose_world(
        nouns(spots=(spot("hall"),), item_specs=(_ROPE,), characters=(character("alice", "hall"), bob))
    )
    store = SqliteWorldStore.create(
        ":memory:", world_id=_WORLD, scenario="s", scenario_hash="h", design=design, random=SeedableRandomSource(0)
    )
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    return design, store.session()


class TestChoiceWordingForPerson:
    """ChoiceWording.for_person が、その人に見えている相手の持ち物から、相手への操作の品物の選択肢を作ることを保証する。"""

    def test_items_seen_on_the_other_person_are_offered_by_name(self) -> None:
        """アリスに見えているボブの手の縄が、ボブへの操作の品物の選択肢に、種類の名前で並ぶ。"""
        design, session = _opened_world()
        rope = session.facts().inventory(_BOB).items()[0]

        wording = ChoiceWording.for_person(_ALICE, session.facts(), design)

        assert wording.arguments_toward(_LOOT, _BOB) == (
            OfferedItemPick(_LOOT_VALUE, (OfferedStep(_LOOT_VALUE, DisplayName("rope"), rope),)),
        )

    def test_fainted_person_is_offered_no_items_on_others(self) -> None:
        """倒れたアリスには何も見えないので、ボブへの操作の品物の選択肢は空になる。"""
        design, session = _opened_world()
        session.aggregates().vitals(_ALICE).take_damage(Damage(999), WorldTick(0), WorldHappening())

        wording = ChoiceWording.for_person(_ALICE, session.facts(), design)

        assert wording.arguments_toward(_LOOT, _BOB) == (OfferedItemPick(_LOOT_VALUE, ()),)
