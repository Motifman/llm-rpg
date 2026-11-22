"""DescribeScene が、事務所にいるゲンに見えているものを場面 (Scene) にして渡し、人の名前を人の穴で渡すことを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import Description, PersonInText, Scene, TextWithPeople
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.describe_scene import DescribeScene, DescribeSceneCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_WORLD = WorldId("world")
_GEN, _SAYO = PersonId("gen"), PersonId("sayo")
_OFFICE = SpotId("company_office")


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


def _scene_of_gen_in_the_office(design: WorldDesign) -> Scene:
    store = SqliteWorldStore.create(
        ":memory:",
        world_id=_WORLD,
        scenario="mine_village_v2",
        scenario_hash="mine_village_v2",
        design=design,
        random=SeedableRandomSource(0),
    )
    OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
    scope = CommandScope(store, CommittedEventsDistributor())

    def move_to_office(session: WorldSession) -> None:
        office = design.nouns.spot_of(_OFFICE)
        for person, name in ((_GEN, "ゲン"), (_SAYO, "サヨ")):
            session.people_register().name(person, DisplayName(name))
            session.aggregates().whereabouts().teleport(PersonBody(person), office, WorldTick(0))

    scope.run(move_to_office)
    return DescribeScene(scope, design)(DescribeSceneCommand(_GEN))


def test_gen_in_the_office_sees_the_safe_the_ways_out_and_sayo(mine_village: WorldDesign) -> None:
    """事務所にいるゲンの場面に、金庫とその見た目、通路の行き先、サヨが出る。サヨは人の穴で渡り、知らせは空。"""
    scene = _scene_of_gen_in_the_office(mine_village)

    assert scene == Scene(
        [
            Description(
                heading="現在地と周囲",
                text=TextWithPeople(
                    template="\n".join(
                        (
                            "鉱山会社の事務所",
                            "鉱山会社の事務所。机と帳簿棚が並び、奥の壁際に重そうな金庫が据えてある。"
                            "屋根の上に古い鐘が吊るされている。",
                            "物:",
                            "- 金庫: 扉は固く閉じている",
                            "- 事務机",
                            "行き先:",
                            "- 井戸",
                            "- 鍛冶場",
                            "- 南の横坑口",
                            "ここには{person_1}がいる。",
                        )
                    ),
                    people={
                        "person_1": PersonInText(handle=3, appearance="綿入れを着込んだ若い娘", visible_name="サヨ")
                    },
                ),
            )
        ],
        notices=(),
    )


def test_being_fills_the_hole_with_the_name_it_sees(mine_village: WorldDesign) -> None:
    """場面の人の穴は、Being の呼び名の決まりで、見えている名前「サヨ」に埋まる。"""
    [surroundings] = _scene_of_gen_in_the_office(mine_village).descriptions
    assert isinstance(surroundings.text, TextWithPeople)

    assert text_naming_people(surroundings.text).endswith("ここにはサヨがいる。")
