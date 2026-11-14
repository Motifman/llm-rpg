from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import UsesWorldDefault
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.people_register_exception import (
    CharacterListedTwiceException,
    PersonAlreadyNamedException,
    PersonNotInRegisterException,
    PersonNotNamedException,
)
from ai_rpg_world.game_world.domain.people import (
    PeopleRegister,
    PeopleRegisterMemento,
    PersonHandle,
    PersonName,
    PersonNamedEvent,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId, SpotId, WorldId
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import compose_world, nouns, spot

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_STRANGER = PersonId("stranger")


def _character(person: PersonId, appearance: str = "背の高い人") -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=person,
        appearance=DescriptionText(appearance),
        spawn_spot=SpotId("beach"),
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
    )


def _register() -> PeopleRegister:
    return PeopleRegister.from_characters(
        _WORLD,
        (_character(_BOB, "赤い帽子の人"), _character(_ALICE, "背の高い人"), _character(_CAROL, "杖をついた人")),
    )


class TestFromCharacters:
    """PeopleRegister.from_characters が、登場人物の宣言から番号と見た目の名簿を作ることを保証する。"""

    def test_handles_are_numbered_from_zero_in_declaration_order(self) -> None:
        """登場人物の宣言の順 (bob, alice, carol) に、番号が 0, 1, 2 と振られる。PersonId の並びには従わない。"""
        register = _register()

        assert register.handle_of(_BOB) == PersonHandle(0)
        assert register.handle_of(_ALICE) == PersonHandle(1)
        assert register.handle_of(_CAROL) == PersonHandle(2)

    def test_appearance_comes_from_the_character_declaration(self) -> None:
        """appearance_of は、その人の CharacterDeclaration.appearance を返す。"""
        assert _register().appearance_of(_CAROL) == DescriptionText("杖をついた人")

    def test_keeps_the_world_as_its_id(self) -> None:
        """世界に 1 つの集約として、WorldId を持つ。開いただけではイベントをためない。"""
        register = _register()

        assert register.world == _WORLD
        assert register.get_events() == []

    def test_declaring_a_character_twice_raises_domain_exception(self) -> None:
        """同じ人の宣言を 2 回渡すと CharacterListedTwiceException を投げる。"""
        with pytest.raises(CharacterListedTwiceException):
            PeopleRegister.from_characters(_WORLD, (_character(_ALICE), _character(_ALICE)))


class TestConstructor:
    """PeopleRegister のコンストラクタが、名簿に無い人の名前を受け取らないことを保証する。"""

    def test_name_of_person_not_in_register_is_refused(self) -> None:
        """登場人物が alice だけの名簿に、stranger の名前を渡して作ると PersonNotInRegisterException を投げる。"""
        with pytest.raises(PersonNotInRegisterException):
            PeopleRegister(_WORLD, (_character(_ALICE),), {_STRANGER: DisplayName("旅人")})


class TestName:
    """PeopleRegister.name が、人の名前を記録してイベントをためることを保証する。"""

    def test_naming_records_the_name_and_emits_person_named_event(self) -> None:
        """alice に「ミナ」を記録すると、name_of がそれを返し、PersonNamedEvent が 1 つたまる。"""
        register = _register()

        register.name(_ALICE, DisplayName("ミナ"))

        assert register.name_of(_ALICE) == DisplayName("ミナ")
        events = register.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PersonNamedEvent)
        assert (events[0].world, events[0].person, events[0].name) == (_WORLD, _ALICE, DisplayName("ミナ"))

    def test_naming_with_the_same_name_again_changes_nothing(self) -> None:
        """記録済みの名前と同じ名前をもう一度記録しても、断らず、イベントもためない。"""
        register = _register()
        register.name(_ALICE, DisplayName("ミナ"))
        register.clear_events()

        register.name(_ALICE, DisplayName("ミナ"))

        assert register.name_of(_ALICE) == DisplayName("ミナ")
        assert register.get_events() == []

    def test_renaming_with_a_different_name_raises_domain_exception(self) -> None:
        """「ミナ」と記録済みの alice に「ミナミ」を記録すると PersonAlreadyNamedException を投げ、名前は「ミナ」のまま、イベントもためない。"""
        register = _register()
        register.name(_ALICE, DisplayName("ミナ"))
        register.clear_events()

        with pytest.raises(PersonAlreadyNamedException):
            register.name(_ALICE, DisplayName("ミナミ"))

        assert register.name_of(_ALICE) == DisplayName("ミナ")
        assert register.get_events() == []

    def test_naming_a_person_not_in_the_register_raises_domain_exception(self) -> None:
        """登場人物にいない人に名前を記録すると PersonNotInRegisterException を投げ、イベントもためない。"""
        register = _register()

        with pytest.raises(PersonNotInRegisterException):
            register.name(_STRANGER, DisplayName("よそ者"))
        assert register.get_events() == []


class TestReadingsOfPeopleNotInTheRegister:
    """登場人物にいない人を問うと、黙って既定値を返さずにドメイン例外を投げることを保証する。"""

    @pytest.mark.parametrize("reading", ["handle_of", "name_of", "appearance_of"])
    def test_reading_a_person_not_in_the_register_raises_domain_exception(self, reading: str) -> None:
        """handle_of・name_of・appearance_of に登場人物にいない人を渡すと PersonNotInRegisterException を投げる。"""
        register = _register()

        with pytest.raises(PersonNotInRegisterException):
            getattr(register, reading)(_STRANGER)


class TestNameOfUnnamedPerson:
    """名前をまだ記録していない人の名前を問うと、黙って空の名前を返さずに断ることを保証する。"""

    def test_name_of_a_person_not_yet_named_raises_domain_exception(self) -> None:
        """登場人物にいるが名前を記録していない bob に name_of を呼ぶと PersonNotNamedException を投げる。"""
        register = _register()
        register.name(_ALICE, DisplayName("ミナ"))

        with pytest.raises(PersonNotNamedException):
            register.name_of(_BOB)


_DESIGN = compose_world(
    nouns(
        spots=(spot("beach"),),
        characters=(
            _character(_BOB, "赤い帽子の人"),
            _character(_ALICE, "背の高い人"),
            _character(_CAROL, "杖をついた人"),
        ),
    )
)


class TestPeopleRegisterMemento:
    """PeopleRegister を memento から作り直すと、名前が元と同じになり、番号と見た目は宣言から同じに作られ、イベントは出ないことを保証する。"""

    def test_rebuilt_register_answers_like_the_original(self) -> None:
        """alice をアリスと名付けたあと作り直すと、memento も名前・番号・見た目の答えも元と同じで、carol はまだ名前が無い。"""
        register = _register()
        register.name(_ALICE, DisplayName("アリス"))

        rebuilt = rebuilt_from_memento(register, _DESIGN.nouns)

        assert rebuilt.memento() == register.memento()
        assert rebuilt.memento() != _register().memento()
        assert rebuilt.world == _WORLD
        assert rebuilt.name_of(_ALICE) == DisplayName("アリス")
        assert rebuilt.handle_of(_ALICE) == register.handle_of(_ALICE)
        assert rebuilt.appearance_of(_CAROL) == DescriptionText("杖をついた人")
        with pytest.raises(PersonNotNamedException):
            rebuilt.name_of(_CAROL)

    def test_rebuilding_records_no_event(self) -> None:
        """名付けたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        register = _register()
        register.name(_ALICE, DisplayName("アリス"))

        assert rebuilt_from_memento(register, _DESIGN.nouns).get_events() == []


class TestPeopleRegisterMementoRefusals:
    """PeopleRegister の memento が、宣言に無い人の名前や同じ人の名前の重なりを持つとき、作り直しを断ることを保証する。"""

    def test_name_of_person_not_declared_is_refused(self) -> None:
        """宣言に無い stranger の名前を持つ memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = PeopleRegisterMemento(
            world_id=_WORLD, names=frozenset({PersonName(_STRANGER, DisplayName("謎の人"))})
        )

        with pytest.raises(UndeclaredNounException):
            PeopleRegister.from_memento(memento, _DESIGN.nouns)

    def test_two_names_for_one_person_is_refused(self) -> None:
        """alice にアリスとアリサの 2 つの名前がある memento を作ると、RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            PeopleRegisterMemento(
                world_id=_WORLD,
                names=frozenset({PersonName(_ALICE, DisplayName("アリス")), PersonName(_ALICE, DisplayName("アリサ"))}),
            )
