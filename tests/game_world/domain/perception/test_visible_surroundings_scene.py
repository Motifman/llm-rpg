"""VisibleSurroundings.scene_with が、見えているものだけを場面の文にし、人を人の穴で渡すことを保証する。

見え方 (明るさ、暗がり、見分けられるか) は VisibleSurroundings.seen_with の規則で決まり、場面の文はそれをそのまま文にする。
"""

from __future__ import annotations

from ai_rpg_world.being.contract import Description, PersonInText, Scene, TextWithPeople, UnidentifiedPerson
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesNothing, SeesShapes
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, SpotId
from tests.game_world.domain.perception._surroundings_builders import contents, item, passage, person, thing
from tests.game_world.support.world_design_for_tests import surroundings_texts

_ITEM_NAMES = {"oil_1": "ランプの油", "oil_2": "ランプの油", "rope": "縄"}


class _Names:
    def spot_name(self, spot: SpotId) -> DisplayName:
        return DisplayName(f"{spot.value} の名前")

    def item_name(self, item: ItemInstanceId) -> DisplayName:
        return DisplayName(_ITEM_NAMES[item.value])


def _text(surroundings: VisibleSurroundings) -> str | TextWithPeople:
    [description] = surroundings.scene_with(surroundings_texts(), _Names()).descriptions
    assert description.heading == "現在地と周囲"
    return description.text


class TestClearSight:
    """明るいとき、場所・物とその見た目・行き先・落ちている品物・人が場面の文に出ることを保証する。"""

    def test_everything_seen_is_written_in_order(self) -> None:
        """場所の名前と説明、物 (見た目つき・見た目なし)、行き先、品物 (同じ名前は数を添える)、人の順に並ぶ。"""
        safe = thing("金庫", look=DescriptionText("扉は固く閉じている"))
        desk = thing("机")
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(),
            contents(
                objects=(safe, desk),
                passages=(passage("to_well", to="well"), passage("to_smithy", to="smithy")),
                ground_items=(item("oil_1"), item("rope"), item("oil_2")),
                people=(person(1),),
            ),
        )

        assert _text(surroundings) == TextWithPeople(
            template="\n".join(
                (
                    "mine_depths",
                    "mine_depths の説明",
                    "物:",
                    "- 金庫: 扉は固く閉じている",
                    "- 机",
                    "行き先:",
                    "- well の名前",
                    "- smithy の名前",
                    "落ちている品物:",
                    "- ランプの油 ×2",
                    "- 縄",
                    "ここには{person_1}がいる。",
                )
            ),
            people={"person_1": PersonInText(handle=1, appearance="1 番の見た目", visible_name=None)},
        )

    def test_two_passages_to_the_same_spot_make_one_destination(self) -> None:
        """同じ場所へ続く通路が 2 本あっても、行き先は 1 行になる。行動の選択肢の行き先の候補と同じ数になる。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(passages=(passage("upper", to="well"), passage("lower", to="well")))
        )

        assert _text(surroundings) == "mine_depths\nmine_depths の説明\n行き先:\n- well の名前"

    def test_scene_without_people_is_plain_text(self) -> None:
        """人がいない場面は、人の穴を持たない文字のまま渡り、空の節 (物・行き先・品物) は見出しごと出ない。"""
        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents())

        assert _text(surroundings) == "mine_depths\nmine_depths の説明"

    def test_braces_in_names_stay_as_letters(self) -> None:
        """物の名前や見た目に括弧があっても、人の穴にはならず、文字のまま出る。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(objects=(thing("{札}", look=DescriptionText("{読めない}")),))
        )

        assert _text(surroundings) == "mine_depths\nmine_depths の説明\n物:\n- {札}: {読めない}"


class TestInTheDark:
    """暗いときに場面に出るものが、VisibleSurroundings の見え方の規則どおりになることを保証する。"""

    def test_shapes_show_people_unidentified_and_hide_ground_items(self) -> None:
        """薄暗いとき、人は見分けのつかない人の穴で出て、落ちている品物と暗いと見えない物は出ない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesShapes(),
            contents(objects=(thing("机"),), ground_items=(item("rope"),), people=(person(1),)),
        )

        assert _text(surroundings) == TextWithPeople(
            template="mine_depths\nmine_depths の説明\nここには{person_1}がいる。",
            people={"person_1": UnidentifiedPerson()},
        )

    def test_pitch_dark_hides_description_and_people(self) -> None:
        """真っ暗なとき、場所の説明の代わりに何も見えないことを書き、人も暗いと見えない物も出ない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesNothing(),
            contents(
                objects=(thing("机"), thing("光る苔", seen_in_dark=True)),
                passages=(passage("to_well", to="well"),),
                people=(person(1),),
            ),
        )

        assert _text(surroundings) == ("mine_depths\n真っ暗で、何も見えない。\n物:\n- 光る苔\n行き先:\n- well の名前")


class TestNothingInView:
    """見ている場所が無い人 (倒れている、移動中など) の場面を保証する。"""

    def test_nothing_in_view_gives_an_empty_scene(self) -> None:
        """何も見えていない人には、説明の無い空の場面を渡す。"""
        assert NothingInView().scene_with(surroundings_texts(), _Names()) == Scene()


def test_scene_is_a_single_description() -> None:
    """場面の文は「現在地と周囲」の見出しを持つ 1 つの説明になり、知らせは空のまま渡る。"""
    scene = VisibleSurroundings.seen_with(SeesClearly(), contents()).scene_with(surroundings_texts(), _Names())

    assert scene == Scene([Description(heading="現在地と周囲", text="mine_depths\nmine_depths の説明")])
