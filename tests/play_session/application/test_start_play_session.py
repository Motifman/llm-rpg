from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.being.contract import Introduction
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import BeingNotFoundException
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.domain.cast import Casting
from ai_rpg_world.play_session.domain.play_session_exception import (
    CastNotFoundException,
    CastValidationException,
    PersonNotCastException,
)
from tests.play_session.mine_village_session import ENVIRONMENT_NAME, WORLD, MineVillageSession

_GEN = PersonId("gen")


class TestStartPlaySession:
    """StartPlaySession が、廃坑の山村 v2 を開き、4 人の Being を人柄から用意して、入るときの材料を渡して入れることを保証する。"""

    def test_gen_is_prepared_with_name_and_first_person_from_the_scenario(self) -> None:
        """ゲンの Being は、シナリオの人柄どおり名前「ゲン」と一人称「俺」で用意される。"""
        session = MineVillageSession().started()

        persona = session.beings.get(BeingId("gen")).persona

        assert (persona.name, persona.first_person) == ("ゲン", "俺")

    def test_every_being_name_is_given_to_the_world(self) -> None:
        """世界の名簿で、4 人の登場人物にそれぞれ Being の名前 (ゲン・サヨ・ハル・ミオ) が付く。"""
        session = MineVillageSession().started()

        names = session.scope.run(
            lambda world: {
                person: world.facts().people_register().name_of(PersonId(person)).text
                for person in ("gen", "sayo", "haru", "mio")
            }
        )

        assert names == {"gen": "ゲン", "sayo": "サヨ", "haru": "ハル", "mio": "ミオ"}

    def test_every_being_enters_the_world(self) -> None:
        """4 人の Being がどれも、世界の識別子と環境の名前「廃坑の山村」の環境に入っている。"""
        session = MineVillageSession().started()

        attachments = {being: session.beings.get(BeingId(being)).attachment for being in ("gen", "sayo", "haru", "mio")}

        assert set(attachments.values()) == {
            BeingAttachment(environment_id=WORLD.value, environment_name=ENVIRONMENT_NAME)
        }

    def test_gens_orientation_has_introduction_premises_and_what_he_knows(self) -> None:
        """ゲンの案内には導入・前提・「あなたが知っていること」が並び、知っていることに金庫の番号 1907 がある。"""
        session = MineVillageSession().started()

        descriptions = tuple(session.casts.get(WORLD).orientation_of(_GEN).descriptions)

        assert [d.heading for d in descriptions] == ["この世界について", "この世界の前提", "あなたが知っていること"]
        known_facts = descriptions[2].text
        assert isinstance(known_facts, str) and "1907" in known_facts

    def test_gens_imposed_goal_is_only_his_objective(self) -> None:
        """ゲンに課された目的は「サヨと二人そろって、坑道の奥の昇降機で外へ出る。」だけになる。"""
        session = MineVillageSession().started()

        entry = session.casts.get(WORLD).entry_of(_GEN)

        assert entry.imposed_goal == "サヨと二人そろって、坑道の奥の昇降機で外へ出る。"

    def test_gen_is_introduced_to_sayo_only(self) -> None:
        """ゲンの紹介にはサヨだけが入り、ハルとミオは入らない。ゲンの知り合いにもサヨだけが記録される。"""
        session = MineVillageSession().started()

        entry = session.casts.get(WORLD).entry_of(_GEN)
        known = [a.name for a in session.acquaintances.list_by_being(BeingId("gen"))]

        assert tuple(entry.introductions) == (Introduction(name="サヨ"),)
        assert known == ["サヨ"]

    def test_entry_and_orientation_given_to_each_being_are_announced(self) -> None:
        """4 人それぞれに BeingCastInWorldEvent が 1 件ずつ出て、ゲンのものは Being gen と、ゲンの課された目的・紹介 (サヨ)・案内を持つ。"""
        session = MineVillageSession().started()

        announced = {event.person: event for event in session.cast_events}

        assert len(session.cast_events) == 4
        assert {person.value for person in announced} == {"gen", "sayo", "haru", "mio"}
        gen = announced[_GEN]
        assert (gen.being_id, gen.entry.imposed_goal, tuple(gen.entry.introductions)) == (
            BeingId("gen"),
            "サヨと二人そろって、坑道の奥の昇降機で外へ出る。",
            (Introduction(name="サヨ"),),
        )
        assert [d.heading for d in gen.orientation.descriptions] == [
            "この世界について",
            "この世界の前提",
            "あなたが知っていること",
        ]

    def test_casting_decides_which_being_plays_each_person(self) -> None:
        """配役でゲンを Being wanderer に当てると、ゲンの人柄の Being wanderer が用意されて入り、Being gen は用意されない。"""
        session = MineVillageSession()
        casting = Casting({**session.command.casting.beings, _GEN: BeingId("wanderer")})

        session.start(replace(session.command, casting=casting))

        assert session.beings.get(BeingId("wanderer")).persona.name == "ゲン"
        with pytest.raises(BeingNotFoundException):
            session.beings.get(BeingId("gen"))

    def test_refused_brief_opens_no_world_and_prepares_no_being(self) -> None:
        """ゲンが知っているサヨを配役から外すと、ゲンへの紹介が組めずに PersonNotCastException で断り、世界は開かず、どの Being も用意しない。
        同じ世界を、サヨを入れた配役で開き直せる。"""
        session = MineVillageSession(without=("sayo",))

        with pytest.raises(PersonNotCastException):
            session.start(session.command)

        with pytest.raises(BeingNotFoundException):
            session.beings.get(BeingId("haru"))
        with pytest.raises(CastNotFoundException):
            session.casts.get(WORLD)
        session.start(MineVillageSession().command)
        assert session.casts.get(WORLD).entry_of(_GEN).imposed_goal is not None


class TestStartPlaySessionRefusesBadCasting:
    """StartPlaySession が、配役の無い役と名前の無い人柄を、世界を開く前に断ることを保証する。"""

    def test_role_not_in_casting_is_refused_before_opening_the_world(self) -> None:
        """配役にゲンが無いのにゲンの役があると PersonNotCastException で断り、配役は保存されず、どの Being も用意しない。"""
        session = MineVillageSession()
        casting = Casting({p: b for p, b in session.command.casting.beings.items() if p != _GEN})

        with pytest.raises(PersonNotCastException):
            session.start(replace(session.command, casting=casting))

        with pytest.raises(CastNotFoundException):
            session.casts.get(WORLD)
        with pytest.raises(BeingNotFoundException):
            session.beings.get(BeingId("sayo"))

    def test_role_without_being_name_is_refused_before_opening_the_world(self) -> None:
        """ゲンの人柄の欄に名前が無いと CastValidationException で断り、配役は保存されない。紹介に使う名前が無いため。"""
        session = MineVillageSession()
        roles = tuple(
            replace(role, persona_fields={"first_person": "俺"}) if role.person == _GEN else role
            for role in session.command.roles
        )

        with pytest.raises(CastValidationException):
            session.start(replace(session.command, roles=roles))

        with pytest.raises(CastNotFoundException):
            session.casts.get(WORLD)
