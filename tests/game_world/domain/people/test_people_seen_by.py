from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.exception.people_register_exception import PersonNotNamedException
from ai_rpg_world.game_world.domain.people import (
    NoVisibleName,
    PeopleAsSeen,
    PeopleRegister,
    PeopleSeenBy,
    PersonHandle,
    PersonRef,
    TextWithUnassignedPeople,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId, SpotId, WorldId

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")


def _character(person: PersonId, appearance: str) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=person,
        appearance=DescriptionText(appearance),
        spawn_spot=SpotId("beach"),
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
    )


def _register() -> PeopleRegister:
    register = PeopleRegister.from_characters(
        WorldId("island"),
        (_character(_ALICE, "背の高い人"), _character(_BOB, "赤い帽子の人"), _character(_CAROL, "杖をついた人")),
    )
    register.name(_ALICE, DisplayName("ミナ"))
    register.name(_BOB, DisplayName("トオル"))
    register.name(_CAROL, DisplayName("ハル"))
    return register


def _seen_by_alice(*, name_tags: bool, knows_at_start: frozenset[PersonId] = frozenset()) -> PeopleSeenBy:
    return PeopleSeenBy(viewer=_ALICE, register=_register(), name_tags=name_tags, knows_at_start=knows_at_start)


class TestWorldWithNameTags:
    """名札の世界 (name_tags が真) で、PeopleSeenBy.ref_of が誰にでも名前を出すことを保証する。"""

    def test_a_stranger_is_seen_with_their_name(self) -> None:
        """名札の世界では、alice が最初から知らない bob も、番号・見た目・名前を持つ PersonRef になる。"""
        ref = _seen_by_alice(name_tags=True).ref_of(_BOB)

        assert ref == PersonRef(
            handle=PersonHandle(1), appearance=DescriptionText("赤い帽子の人"), visible_name=DisplayName("トオル")
        )


class TestWorldWithoutNameTags:
    """名札の無い世界で、PeopleSeenBy.ref_of が見る人の知っている相手と見る人自身にだけ名前を出すことを保証する。"""

    def test_a_person_known_at_start_is_seen_with_their_name(self) -> None:
        """alice の knows_at_start に bob がいれば、bob は名前つきの PersonRef になる。"""
        ref = _seen_by_alice(name_tags=False, knows_at_start=frozenset({_BOB})).ref_of(_BOB)

        assert ref.visible_name == DisplayName("トオル")

    def test_the_viewer_sees_their_own_name(self) -> None:
        """knows_at_start に自分が入っていなくても、alice から見た alice は名前つきの PersonRef になる。"""
        ref = _seen_by_alice(name_tags=False).ref_of(_ALICE)

        assert ref == PersonRef(
            handle=PersonHandle(0), appearance=DescriptionText("背の高い人"), visible_name=DisplayName("ミナ")
        )

    def test_a_stranger_is_seen_by_appearance_only(self) -> None:
        """knows_at_start に無い carol は、番号と見た目だけを持ち、名前が NoVisibleName の PersonRef になる。"""
        ref = _seen_by_alice(name_tags=False, knows_at_start=frozenset({_BOB})).ref_of(_CAROL)

        assert ref == PersonRef(
            handle=PersonHandle(2), appearance=DescriptionText("杖をついた人"), visible_name=NoVisibleName()
        )


class TestPersonNotYetNamed:
    """名前を出すべき相手の名前がまだ記録されていないとき、PeopleSeenBy.ref_of が見た目だけに落とさず断ることを保証する。"""

    def test_a_person_whose_name_should_show_but_is_not_recorded_raises_domain_exception(self) -> None:
        """名札の世界で、名簿にいるが名前を記録していない dave を alice が見ると、PersonNotNamedException を投げる。"""
        dave = PersonId("dave")
        register_with_dave = PeopleRegister.from_characters(
            WorldId("island"), (_character(_ALICE, "背の高い人"), _character(dave, "髭の人"))
        )
        register_with_dave.name(_ALICE, DisplayName("ミナ"))
        view = PeopleSeenBy(viewer=_ALICE, register=register_with_dave, name_tags=True, knows_at_start=frozenset())

        with pytest.raises(PersonNotNamedException):
            view.ref_of(dave)

    def test_an_unnamed_stranger_in_a_world_without_name_tags_is_seen_by_appearance(self) -> None:
        """名札の無い世界で、知らない相手は名前を問わないので、名前を記録していなくても見た目だけの PersonRef になる。"""
        dave = PersonId("dave")
        register = PeopleRegister.from_characters(
            WorldId("island"), (_character(_ALICE, "背の高い人"), _character(dave, "髭の人"))
        )
        view = PeopleSeenBy(viewer=_ALICE, register=register, name_tags=False, knows_at_start=frozenset())

        assert view.ref_of(dave) == PersonRef(
            handle=PersonHandle(1), appearance=DescriptionText("髭の人"), visible_name=NoVisibleName()
        )


class TestAsPeopleAsSeen:
    """PeopleSeenBy が PeopleAsSeen として文に見る人ごとの呼び方を当てられることを保証する。"""

    def test_text_about_people_seen_by_assigns_refs_from_the_viewers_side(self) -> None:
        """「{actor}が{target}に手を振った」を alice から見ると、知っている bob は名前つき、知らない carol は見た目だけで当たる。"""
        view: PeopleAsSeen = _seen_by_alice(name_tags=False, knows_at_start=frozenset({_BOB}))
        text = TextWithUnassignedPeople("{actor}が{target}に手を振った").about({"actor": _BOB, "target": _CAROL})

        assigned = text.seen_by(view)

        actor, target = assigned.people["actor"], assigned.people["target"]
        assert isinstance(actor, PersonRef) and isinstance(target, PersonRef)
        assert actor.visible_name == DisplayName("トオル")
        assert target.visible_name == NoVisibleName()
