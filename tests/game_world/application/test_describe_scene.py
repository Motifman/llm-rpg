"""DescribeScene が、事務所にいるゲンに見えているものを場面 (Scene) にして渡し、人の名前を人の穴で渡すことを保証する。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import Here, PersonInText, Scene, TextWithPeople
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.describe_scene import DescribeScene, DescribeSceneCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.design_flaw.design_location import DesignLocation
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    Damage,
    DisplayName,
    ObjectId,
    PersonId,
    SpotId,
    WorldId,
    WorldTick,
)
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
    return _scene_of_gen_at(design, _OFFICE)


def _scene_of_gen_at(
    design: WorldDesign, spot: SpotId, prepare: Callable[[WorldSession], None] = lambda session: None
) -> Scene:
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

    def move_there(session: WorldSession) -> None:
        there = design.nouns.spot_of(spot)
        for person, name in ((_GEN, "ゲン"), (_SAYO, "サヨ")):
            session.people_register().name(person, DisplayName(name))
            session.aggregates().whereabouts().teleport(PersonBody(person), there, WorldTick(0))

    scope.run(move_there)
    scope.run(prepare)
    return DescribeScene(scope, design)(DescribeSceneCommand(_GEN))


def test_gen_in_the_office_sees_the_safe_the_ways_out_and_sayo(mine_village: WorldDesign) -> None:
    """事務所にいるゲンの場面に、古い run と同じ行の形で、説明・雰囲気・時刻・時刻帯・接続先・金庫とその見た目・サヨ・ゲンの持ち物・ゲンの身体の状態が出る。サヨは人の穴で渡り、知らせは空。"""
    scene = _scene_of_gen_in_the_office(mine_village)

    assert scene == Scene(
        here=Here(
            place="鉱山会社の事務所",
            heading="現在地と周囲",
            text=TextWithPeople(
                template="\n".join(
                    (
                        "  鉱山会社の事務所。机と帳簿棚が並び、奥の壁際に重そうな金庫が据えてある。"
                        "屋根の上に古い鐘が吊るされている。",
                        "雰囲気: 明るさ: 明るい / 音: 鐘の綱が風に揺れて柱をこする音 / 気温: 寒い",
                        "現在時刻: Day 1 深夜 0:00",
                        "時刻帯: 未明 (暗い)",
                        "接続先:",
                        '  - "井戸と鉱山会社の事務所の道" → "井戸"（通行可）',
                        '  - "鍛冶場と鉱山会社の事務所の道" → "鍛冶場"（通行可）',
                        '  - "鉱山会社の事務所と南の横坑口の道" → "南の横坑口"（通行可）',
                        "オブジェクト:",
                        '  - "金庫" (扉は固く閉じている) — 壁際に据えられた重い鉄の金庫。'
                        "四桁の番号を合わせるダイヤルが付いている。",
                        '  - "事務机" — 埃をかぶった事務机。引き出しが半分開いている。',
                        "同じ場所にいるプレイヤー:",
                        '  - "{person_1}"',
                        "所持アイテム:",
                        '  - "カンテラ" — 油を足して灯す手提げのカンテラ。',
                        '  - "カンテラの油" x3 — カンテラに足す油の小瓶。',
                        "身体の状態:",
                        "  HP: 良好（100/100）",
                        "  空腹: 問題なし（0/100）",
                        "  疲労: 問題なし（0/100）",
                    )
                ),
                people={"person_1": PersonInText(handle=3, appearance="綿入れを着込んだ若い娘", visible_name="サヨ")},
            ),
        ),
    )


def test_being_fills_the_hole_with_the_name_it_sees(mine_village: WorldDesign) -> None:
    """場面の人の穴は、Being の呼び名の決まりで、見えている名前「サヨ」に埋まる。"""
    surroundings = _scene_of_gen_in_the_office(mine_village).here
    assert surroundings is not None
    assert isinstance(surroundings.text, TextWithPeople)

    assert text_naming_people(surroundings.text).splitlines()[-9:-7] == [
        "同じ場所にいるプレイヤー:",
        '  - "サヨ"',
    ]


def test_gen_at_the_south_adit_mouth_sees_the_snow_and_the_night_like_the_old_run(mine_village: WorldDesign) -> None:
    """屋外の南の横坑口にいるゲンの場面は、古い run の手本と同じく、夜で一段暗い「薄暗い」と、屋外の天候「雪」と、暗い時刻帯「未明」を書く。"""
    surroundings = _scene_of_gen_at(mine_village, SpotId("south_adit_mouth")).here
    assert surroundings is not None
    assert isinstance(surroundings.text, TextWithPeople)

    assert surroundings.text.template.splitlines()[:5] == [
        "  村の南の斜面に口を開けた横坑。坑口には朽ちかけた木枠が組まれている。",
        "雰囲気: 明るさ: 薄暗い / 音: 横坑の奥から響く水の音 / 気温: 寒い",
        "天候: 雪（屋外）",
        "現在時刻: Day 1 深夜 0:00",
        "時刻帯: 未明 (暗い)",
    ]


_HERE_IN_TEST = DesignLocation("test", "describe_scene", "nouns")


def _object_lines(scene: Scene) -> list[str]:
    assert scene.here is not None
    text = scene.here.text
    lines = (text.template if isinstance(text, TextWithPeople) else text).splitlines()
    return lines[lines.index("オブジェクト:") + 1 :]


def test_empty_bucket_says_drawing_water_is_not_possible_now(mine_village: WorldDesign) -> None:
    """釣瓶の水が尽きると、釣瓶の行の下に「いまできない: 水を汲む」が理由つきで出る。物の数の条件で断られるため (古い run と同じ)。"""

    def empty_the_bucket(session: WorldSession) -> None:
        water = mine_village.nouns.object_state_key("well_bucket", "water", _HERE_IN_TEST)
        session.aggregates().object_state(ObjectId("well_bucket")).take_from_stock(water, Count(4), WorldTick(0))

    lines = _object_lines(_scene_of_gen_at(mine_village, SpotId("well"), empty_the_bucket))

    assert lines[:2] == [
        '  - "井戸の釣瓶" — 滑車に掛かった古い釣瓶。',
        "      いまできない: 水を汲む（釣瓶は空のまま上がってきた。底の水が溜まるのを待つしかない。）",
    ]


def test_opened_safe_shows_no_line_of_what_cannot_be_done(mine_village: WorldDesign) -> None:
    """金庫を開けたあとも、金庫の行の下に「いまできない」は出ない。旗の条件で断られる操作は、古い run と同じく選べる操作の一覧に残すため。"""
    lines = _object_lines(
        _scene_of_gen_at(
            mine_village,
            _OFFICE,
            lambda session: (
                session.aggregates()
                .flags()
                .raise_flag(mine_village.nouns.flag("safe_opened", _HERE_IN_TEST), WorldTimePassing(WorldTick(0)))
            ),
        )
    )

    assert not any("いまできない" in line for line in lines)


def test_closed_gate_hides_closing_it(mine_village: WorldDesign) -> None:
    """閉じている北の坑道の水門には、「水門を閉じる」がいまできないとしても出ない。伏せる印のある操作は、条件を満たさないあいだ存在ごと伏せるため。"""
    lines = _object_lines(_scene_of_gen_at(mine_village, SpotId("north_tunnel")))

    assert not any("水門を閉じる" in line for line in lines)


def _body_and_belongings(scene: Scene) -> list[str]:
    assert scene.here is not None and isinstance(scene.here.text, TextWithPeople)
    lines = scene.here.text.template.splitlines()
    return lines[lines.index("所持アイテム:") :]


def test_held_lantern_is_marked_and_hurt_gen_sees_the_hit_points_tier(mine_village: WorldDesign) -> None:
    """カンテラを手に持ち、HP が 30/100 まで減ったゲンの場面は、カンテラに「(手に持っている)」を付け、HP を「危険（30/100）」と書く。"""

    def hold_lantern_and_get_hurt(session: WorldSession) -> None:
        inventory = session.aggregates().inventory(_GEN)
        lantern = next(
            item
            for item in inventory.items()
            if mine_village.nouns.item_spec_of(session.facts().item(item).spec_id).name == DisplayName("カンテラ")
        )
        spec = mine_village.nouns.item_spec_of(session.facts().item(lantern).spec_id)
        inventory.hold(lantern, spec.hands_needed)
        session.aggregates().vitals(_GEN).take_damage(Damage(70), WorldTick(0), WorldHappening())

    scene = _scene_of_gen_at(mine_village, _OFFICE, hold_lantern_and_get_hurt)

    assert _body_and_belongings(scene) == [
        "所持アイテム:",
        '  - "カンテラ" — 油を足して灯す手提げのカンテラ。 (手に持っている)',
        '  - "カンテラの油" x3 — カンテラに足す油の小瓶。',
        "身体の状態:",
        "  HP: 危険（30/100）",
        "  空腹: 問題なし（0/100）",
        "  疲労: 問題なし（0/100）",
    ]


def test_held_one_of_the_same_kind_is_listed_apart_from_the_packed_ones(mine_village: WorldDesign) -> None:
    """3 本の油のうち 1 本を手に持つと、手の 1 本は「(手に持っている)」の行、荷の 2 本は「x2」の行に分かれる。"""

    def hold_one_oil(session: WorldSession) -> None:
        inventory = session.aggregates().inventory(_GEN)
        oil = next(
            item
            for item in inventory.items()
            if mine_village.nouns.item_spec_of(session.facts().item(item).spec_id).name == DisplayName("カンテラの油")
        )
        inventory.hold(oil, mine_village.nouns.item_spec_of(session.facts().item(oil).spec_id).hands_needed)

    lines = _body_and_belongings(_scene_of_gen_at(mine_village, _OFFICE, hold_one_oil))

    assert '  - "カンテラの油" — カンテラに足す油の小瓶。 (手に持っている)' in lines
    assert '  - "カンテラの油" x2 — カンテラに足す油の小瓶。' in lines
