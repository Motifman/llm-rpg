"""VisibleSurroundings.scene_with が、見えているものだけを古い run の【現在地と周囲】の行の形で場面の文にし、人を人の穴で渡すことを保証する。

見え方 (明るさ、暗がり、見分けられるか) は VisibleSurroundings.seen_with の規則で決まり、場面の文はそれをそのまま文にする。
"""

from __future__ import annotations

from ai_rpg_world.being.contract import Here, PersonInText, Scene, TextWithPeople, UnidentifiedPerson
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesNothing, SeesShapes
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, SpotId
from tests.game_world.domain.perception._surroundings_builders import conditions, contents, item, passage, person, thing
from tests.game_world.support.world_design_for_tests import clock_wording, surroundings_texts, world_words

_ITEM_NAMES = {"oil_1": "ランプの油", "oil_2": "ランプの油", "rope": "縄"}


class _Names:
    def spot_name(self, spot: SpotId) -> DisplayName:
        return DisplayName(f"{spot.value} の名前")

    def item_name(self, item: ItemInstanceId) -> DisplayName:
        return DisplayName(_ITEM_NAMES[item.value])


def _scene(surroundings: VisibleSurroundings) -> Scene:
    return surroundings.scene_with(surroundings_texts(), _Names(), world_words(), clock_wording())


def _text(surroundings: VisibleSurroundings) -> str | TextWithPeople:
    here = _scene(surroundings).here
    assert here is not None and here.heading == "現在地と周囲" and here.place == "mine_depths"
    return here.text


_TOP = "  mine_depths の説明\n雰囲気: 明るさ: 明るい / 気温: 過ごしやすい"
_NO_OBJECTS = "オブジェクト: (ここには何も無い)"


class TestClearSight:
    """明るいとき、場所の説明・雰囲気・接続先・オブジェクト・落ちている品物・人が、古い run の行の形で場面の文に出ることを保証する。"""

    def test_everything_seen_is_written_in_order(self) -> None:
        """説明、雰囲気、接続先 (通路ごと)、オブジェクト (見た目つきは括弧に入れる)、品物 (同じ名前は数を添える)、人の順に並ぶ。"""
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
            conditions(),
        )

        assert _text(surroundings) == TextWithPeople(
            template="\n".join(
                (
                    _TOP,
                    "接続先:",
                    '  - "to_well の通路" → "well の名前"（通行可）',
                    '  - "to_smithy の通路" → "smithy の名前"（通行可）',
                    "オブジェクト:",
                    '  - "金庫" (扉は固く閉じている) — 金庫 の説明',
                    '  - "机" — 机 の説明',
                    "落ちている品物:",
                    "- ランプの油 ×2",
                    "- 縄",
                    "ここには{person_1}がいる。",
                )
            ),
            people={"person_1": PersonInText(handle=1, appearance="1 番の見た目", visible_name=None)},
        )

    def test_closed_passage_says_why_it_cannot_be_passed(self) -> None:
        """通れない状態の通路は「通行不可 — 状態の名前」と書く。"""
        flooded = passage("to_well", to="well", state="closed")

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(passages=(flooded,)), conditions())

        assert '  - "to_well の通路" → "well の名前"（通行不可 — 閉じている）' in str(_text(surroundings))

    def test_one_way_passage_coming_in_is_not_a_way_out(self) -> None:
        """ここへ入ってくるだけの一方通行の通路は、接続先に出ない。そこからは出られないため。"""
        coming_in = passage("chute", at="well", to="mine_depths", two_way=False)

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(passages=(coming_in,)), conditions())

        assert _text(surroundings) == f"{_TOP}\n{_NO_OBJECTS}"

    def test_each_passage_to_the_same_spot_has_its_own_line(self) -> None:
        """同じ場所へ続く通路が 2 本あると、接続先は通路ごとに 2 行になる。古い run の接続先と同じ。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(passages=(passage("upper", to="well"), passage("lower", to="well"))), conditions()
        )

        assert _text(surroundings) == "\n".join(
            (
                _TOP,
                "接続先:",
                '  - "upper の通路" → "well の名前"（通行可）',
                '  - "lower の通路" → "well の名前"（通行可）',
                _NO_OBJECTS,
            )
        )

    def test_scene_without_objects_says_there_is_nothing(self) -> None:
        """明るくて物が無い場面は、オブジェクトの節を消さず「(ここには何も無い)」と書き、人がいなければ文字のまま渡る。"""
        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(), conditions())

        assert _text(surroundings) == f"{_TOP}\n{_NO_OBJECTS}"

    def test_braces_in_names_stay_as_letters(self) -> None:
        """物の名前や見た目に括弧があっても、人の穴にはならず、文字のまま出る。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(objects=(thing("{札}", look=DescriptionText("{読めない}")),)), conditions()
        )

        assert _text(surroundings) == f'{_TOP}\nオブジェクト:\n  - "{{札}}" ({{読めない}}) — {{札}} の説明'


class TestInTheDark:
    """暗いときに場面に出るものが、VisibleSurroundings の見え方の規則どおりになることを保証する。"""

    def test_shapes_show_people_unidentified_and_say_the_dark_hides_objects(self) -> None:
        """薄暗くて見える物が無いとき、オブジェクトは「暗くて何も見えない」と書き、人は見分けのつかない人の穴で出て、品物は出ない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesShapes(),
            contents(objects=(thing("机"),), ground_items=(item("rope"),), people=(person(1),)),
            conditions(),
        )

        assert _text(surroundings) == TextWithPeople(
            template=f"{_TOP}\nオブジェクト: (暗くて何も見えない。灯りが要る)\nここには{{person_1}}がいる。",
            people={"person_1": UnidentifiedPerson()},
        )

    def test_pitch_dark_hides_description_and_warns_that_more_may_be_hidden(self) -> None:
        """真っ暗なとき、説明の代わりに何も見えないことを書き、暗くても見える物の前に、ほかの物が隠れているかもしれないと書く。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesNothing(),
            contents(
                objects=(thing("机"), thing("光る苔", seen_in_dark=True)),
                passages=(passage("to_well", to="well"),),
                people=(person(1),),
            ),
            conditions(),
        )

        assert _text(surroundings) == "\n".join(
            (
                "  真っ暗で、何も見えない。",
                "雰囲気: 明るさ: 明るい / 気温: 過ごしやすい",
                "接続先:",
                '  - "to_well の通路" → "well の名前"（通行可）',
                "オブジェクト:",
                "  (暗い。灯りがなければ、見えるのはこれだけ)",
                '  - "光る苔" — 光る苔 の説明',
            )
        )


class TestNothingInView:
    """見ている場所が無い人 (倒れている、移動中など) の場面を保証する。"""

    def test_nothing_in_view_gives_an_empty_scene(self) -> None:
        """何も見えていない人には、説明の無い空の場面を渡す。"""
        assert NothingInView().scene_with(surroundings_texts(), _Names(), world_words(), clock_wording()) == Scene()


def test_scene_is_the_place_here() -> None:
    """場面の文は「現在地と周囲」の見出しと場所の名前を持つ「いまいる場所」で渡り、ほかの説明と知らせは空のまま渡る。"""
    scene = _scene(VisibleSurroundings.seen_with(SeesClearly(), contents(), conditions()))

    assert scene == Scene(here=Here(place="mine_depths", heading="現在地と周囲", text=f"{_TOP}\n{_NO_OBJECTS}"))
