from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
from ai_rpg_world.game_world.domain.declaration.verb import NoLook
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesNothing, SeesShapes
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.perception.surroundings import SeenObject, SeenPerson, VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId, SpotSectionId, WorldTick
from tests.game_world.domain.perception._surroundings_builders import (
    conditions,
    contents,
    item,
    passage,
    person,
    section,
    seen,
    thing,
)
from tests.game_world.support.world_design_for_tests import scene_texts


class TestHiddenThingsStayOutOfSurroundings:
    """VisibleSurroundings.seen_with が、まだ現れていない物と通路を見え方にかかわらず場面から外すことを保証する。"""

    def test_unrevealed_passage_is_left_out_even_in_clear_sight(self) -> None:
        """明るくても、現れていない隠し通路は場面の通路に出ず、現れている通路だけが出る。"""
        corridor = passage("corridor")
        secret_tunnel = passage("secret_tunnel", to="old_shaft", revealed=False)

        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(passages=(corridor, secret_tunnel)), conditions()
        )

        assert surroundings.passages == (corridor.passage,)

    def test_unrevealed_object_is_left_out_even_in_clear_sight(self) -> None:
        """明るくても、現れていない隠し扉は場面の物体に出ず、現れている物体だけが出る。"""
        lamp_stand = thing("lamp_stand")
        hidden_door = thing("hidden_door", revealed=False)

        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(objects=(lamp_stand, hidden_door)), conditions()
        )

        assert surroundings.objects == (seen(lamp_stand),)


class TestClearSightShowsEverythingRevealed:
    """VisibleSurroundings.seen_with が SeesClearly のとき、現れているものをすべて場面に出すことを保証する。"""

    def test_people_are_shown_as_the_viewer_refers_to_them(self) -> None:
        """明るいとき、その場にいる人は材料を集める側が当てた PersonRef のまま、居る区画とともに出る。"""
        miner = person(1, section=SpotSectionId("cage"))

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(people=(miner,)), conditions())

        assert surroundings.people == (
            SeenPerson(person=miner.person, section=SpotSectionId("cage"), visible_items=()),
        )

    def test_ground_items_objects_sections_and_description_are_shown(self) -> None:
        """明るいとき、地面の品物、暗いと見えない物体、区画、場所の説明がすべて出る。"""
        cage = section("cage")
        ore_cart = thing("ore_cart", seen_in_dark=False)

        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(),
            contents(sections=(cage,), objects=(ore_cart,), ground_items=(item("rusty_key"),)),
            conditions(),
        )

        assert surroundings.shows_description
        assert surroundings.sections == (cage,)
        assert surroundings.objects == (seen(ore_cart),)
        assert surroundings.ground_items == (item("rusty_key"),)


class TestShapesInTheDark:
    """VisibleSurroundings.seen_with が SeesShapes (暗い) のとき、人を見分けず、暗くても見える物体だけを出すことを保証する。"""

    def test_people_appear_as_unidentified(self) -> None:
        """暗いとき、その場にいる人は Unidentified として、居る区画とともに出る。"""
        miner = person(1, section=SpotSectionId("cage"))

        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(people=(miner,)), conditions())

        assert [(seen.person, seen.section) for seen in surroundings.people] == [
            (Unidentified(), SpotSectionId("cage"))
        ]

    def test_ground_items_are_not_shown(self) -> None:
        """暗いとき、地面に落ちている品物は場面に出ない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesShapes(), contents(ground_items=(item("rusty_key"),)), conditions()
        )

        assert surroundings.ground_items == ()

    def test_only_objects_seen_in_dark_are_shown(self) -> None:
        """暗いとき、物体は seen_in_dark が真のもの (光る苔など) だけが出て、ほかの物体は出ない。"""
        glowing_moss = thing("glowing_moss", seen_in_dark=True)
        ore_cart = thing("ore_cart", seen_in_dark=False)

        surroundings = VisibleSurroundings.seen_with(
            SeesShapes(), contents(objects=(glowing_moss, ore_cart)), conditions()
        )

        assert surroundings.objects == (seen(glowing_moss),)

    def test_description_passages_and_sections_are_still_shown(self) -> None:
        """暗くても、場所の説明は出て、通路と区画も出る。"""
        corridor = passage("corridor")
        cage = section("cage")

        surroundings = VisibleSurroundings.seen_with(
            SeesShapes(), contents(passages=(corridor,), sections=(cage,)), conditions()
        )

        assert surroundings.shows_description
        assert surroundings.passages == (corridor.passage,)
        assert surroundings.sections == (cage,)


class TestNothingInPitchDark:
    """VisibleSurroundings.seen_with が SeesNothing (真っ暗) のとき、人と説明を出さず、手探りで分かる通路と区画は出すことを保証する。"""

    def test_people_and_bodies_are_not_shown(self) -> None:
        """真っ暗なとき、起きている人も倒れている人も場面に出ない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesNothing(), contents(people=(person(1),), bodies=(person(2),)), conditions()
        )

        assert surroundings.people == ()
        assert surroundings.bodies == ()

    def test_description_is_not_shown(self) -> None:
        """真っ暗なとき、shows_description は偽になる。"""
        surroundings = VisibleSurroundings.seen_with(SeesNothing(), contents(), conditions())

        assert not surroundings.shows_description

    def test_passages_and_sections_are_still_shown(self) -> None:
        """真っ暗でも、現れている通路と区画は出る。"""
        corridor = passage("corridor")
        cage = section("cage")

        surroundings = VisibleSurroundings.seen_with(
            SeesNothing(), contents(passages=(corridor,), sections=(cage,)), conditions()
        )

        assert surroundings.passages == (corridor.passage,)
        assert surroundings.sections == (cage,)

    def test_only_objects_seen_in_dark_are_shown_and_no_ground_items(self) -> None:
        """真っ暗なとき、物体は seen_in_dark が真のものだけが出て、地面の品物は出ない。"""
        glowing_moss = thing("glowing_moss", seen_in_dark=True)
        ore_cart = thing("ore_cart", seen_in_dark=False)

        surroundings = VisibleSurroundings.seen_with(
            SeesNothing(), contents(objects=(glowing_moss, ore_cart), ground_items=(item("rusty_key"),)), conditions()
        )

        assert surroundings.objects == (seen(glowing_moss),)
        assert surroundings.ground_items == ()


class TestItemsSeenOnPeople:
    """VisibleSurroundings.seen_with が、起きている人と倒れている人とで見える持ち物を変えることを保証する。"""

    def test_awake_person_shows_only_held_items(self) -> None:
        """明るいとき、起きている人は手に持っている物だけが見え、荷の中の物は見えない。"""
        miner = person(1, held=(item("pickaxe"),), carried=(item("bread"),))

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(people=(miner,)), conditions())

        assert [seen.visible_items for seen in surroundings.people] == [(item("pickaxe"),)]

    def test_body_shows_all_items(self) -> None:
        """明るいとき、倒れている人と死んだ人は、手の物も荷の中の物も、持ち物すべてが見える。"""
        fallen = person(2, held=(item("lantern"),), carried=(item("map"),))

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(bodies=(fallen,)), conditions())

        assert [seen.visible_items for seen in surroundings.bodies] == [(item("lantern"), item("map"))]
        assert [seen.person for seen in surroundings.bodies] == [fallen.person]

    def test_body_appears_as_unidentified_in_the_dark(self) -> None:
        """暗いとき、倒れている人も Unidentified として出る。"""
        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(bodies=(person(2),)), conditions())

        assert [seen.person for seen in surroundings.bodies] == [Unidentified()]


class TestHiddenThingsStayOutInTheDark:
    """VisibleSurroundings.seen_with が、暗くても見える物体であっても、現れていなければ暗がりで出さないことを保証する。"""

    def test_unrevealed_glowing_object_is_left_out_in_shapes(self) -> None:
        """暗いとき、seen_in_dark が真でも現れていない物体 (隠し戸の光る印) は出ない。"""
        hidden_glow = thing("hidden_glow", seen_in_dark=True, revealed=False)

        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(objects=(hidden_glow,)), conditions())

        assert surroundings.objects == ()

    def test_unrevealed_glowing_object_is_left_out_in_pitch_dark(self) -> None:
        """真っ暗なとき、seen_in_dark が真でも現れていない物体は出ない。"""
        hidden_glow = thing("hidden_glow", seen_in_dark=True, revealed=False)

        surroundings = VisibleSurroundings.seen_with(SeesNothing(), contents(objects=(hidden_glow,)), conditions())

        assert surroundings.objects == ()


class TestItemsOnPeopleHiddenInTheDark:
    """VisibleSurroundings.seen_with が SeesShapes (暗い) のとき、地面の品物と同じく人の持ち物も出さないことを保証する。"""

    def test_awake_person_shows_no_held_items(self) -> None:
        """暗いとき、起きている人が手に持っている物は見えず、visible_items は空になる。"""
        miner = person(1, held=(item("pickaxe"),))

        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(people=(miner,)), conditions())

        assert [seen.visible_items for seen in surroundings.people] == [()]

    def test_body_shows_no_items(self) -> None:
        """暗いとき、倒れている人の持ち物は手の物も荷の中の物も見えず、visible_items は空になる。"""
        fallen = person(2, held=(item("lantern"),), carried=(item("map"),))

        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(bodies=(fallen,)), conditions())

        assert [seen.visible_items for seen in surroundings.bodies] == [()]


class TestObjectLooksReachSurroundings:
    """VisibleSurroundings.seen_with が、集めたときに決めた物の見え方を、場面に出る物へそのまま運ぶことを保証する。"""

    def test_look_of_a_seen_object_is_carried_into_surroundings(self) -> None:
        """「開いていて、水の流れる音がする」と決めた水門は、その見え方を持った SeenObject として場面に出る。"""
        floodgate = thing("floodgate", look=DescriptionText("開いていて、水の流れる音がする"))

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(objects=(floodgate,)), conditions())

        assert surroundings.objects == (
            SeenObject(declaration=floodgate.declaration, look=DescriptionText("開いていて、水の流れる音がする")),
        )

    def test_object_without_a_look_is_shown_with_no_look(self) -> None:
        """どの見え方にも当てはまらなかった物は、NoLook を持った SeenObject として場面に出る。"""
        ore_cart = thing("ore_cart")

        surroundings = VisibleSurroundings.seen_with(SeesClearly(), contents(objects=(ore_cart,)), conditions())

        assert surroundings.objects == (SeenObject(declaration=ore_cart.declaration, look=NoLook()),)


def _surroundings_texts() -> SurroundingsTexts:
    return SurroundingsTexts(
        people_here=TextWithUnassignedPeople("ここには{people}がいる。"),
        bodies_here=TextWithUnassignedPeople("{people}が倒れている。"),
        joiner="、",
        waking=TextWithUnassignedPeople("目が覚めた。"),
        darkening=TextWithUnassignedPeople("辺りが暗くなった。"),
        scene=scene_texts(),
    )


_VIEWER = PersonId("viewer")
_NOW = WorldTick(7)


class TestSurroundingsPerceivedAsOneObservation:
    """VisibleSurroundings.perceived_by が、場面の人と倒れた体を 1 つの見える知覚にすることを保証する。

    人も倒れた体もいなければ知覚にしない。いる側の文だけを、人、倒れた体の順につなぐ。
    """

    def test_people_and_bodies_become_one_clear_sight(self) -> None:
        """明るいとき、人と倒れた体が当てた PersonRef のまま 1 つの文に入り、SeesClearly の目立たない知覚になる。"""
        miner, fallen = person(1), person(2)
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(people=(miner,), bodies=(fallen,)), conditions()
        )

        perceived = surroundings.perceived_by(_VIEWER, _surroundings_texts(), _NOW)

        assert perceived == (
            Perceived(
                perceiver=_VIEWER,
                text=TextWithAssignedPeople(
                    "ここには{person_1}がいる。{person_2}が倒れている。",
                    {"person_1": miner.person, "person_2": fallen.person},
                ),
                quality=SeesClearly(),
                happened_at=_NOW,
                calls_attention=False,
            ),
        )

    def test_dim_sight_lists_unidentified_people(self) -> None:
        """薄暗いとき、人は見分けられないまま文に入り、SeesShapes の知覚になる。"""
        surroundings = VisibleSurroundings.seen_with(SeesShapes(), contents(people=(person(1),)), conditions())

        perceived = surroundings.perceived_by(_VIEWER, _surroundings_texts(), _NOW)

        assert [(one.text.people, one.quality) for one in perceived] == [({"person_1": Unidentified()}, SeesShapes())]

    def test_no_people_and_no_bodies_is_not_perceived(self) -> None:
        """明るくても、人も倒れた体もいなければ、物や地面の品物があっても知覚にならない。"""
        surroundings = VisibleSurroundings.seen_with(
            SeesClearly(), contents(objects=(thing("ore_cart"),), ground_items=(item("rusty_key"),)), conditions()
        )

        assert surroundings.perceived_by(_VIEWER, _surroundings_texts(), _NOW) == ()

    def test_people_in_pitch_dark_are_not_perceived(self) -> None:
        """真っ暗では、その場に人がいても知覚にならない。"""
        surroundings = VisibleSurroundings.seen_with(SeesNothing(), contents(people=(person(1),)), conditions())

        assert surroundings.perceived_by(_VIEWER, _surroundings_texts(), _NOW) == ()

    def test_nothing_in_view_is_not_perceived(self) -> None:
        """場面が無い人 (移動中・倒れている人など) には知覚にならない。"""
        assert NothingInView().perceived_by(_VIEWER, _surroundings_texts(), _NOW) == ()
