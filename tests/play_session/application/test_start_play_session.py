from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.being.contract import Introduction
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import BeingNotFoundException
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import FreeToAct
from ai_rpg_world.play_session.domain.cast import Casting
from ai_rpg_world.play_session.domain.play_session_exception import (
    CastNotFoundException,
    CastValidationException,
    PersonNotCastException,
    TurnRoundsNotFoundException,
)
from ai_rpg_world.play_session.domain.turn_rounds import Acted, Waited
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

        assert {(a.environment_id, a.environment_name) for a in attachments.values() if a is not None} == {
            (WORLD.value, ENVIRONMENT_NAME)
        }
        assert all(a is not None for a in attachments.values())

    def test_gens_orientation_is_the_world_premises(self) -> None:
        """ゲンの案内には「世界の前提」だけが並び、知っていることは入らない。"""
        session = MineVillageSession().started()

        descriptions = tuple(session.casts.get(WORLD).orientation_of(_GEN).descriptions)

        assert [d.heading for d in descriptions] == ["世界の前提"]

    def test_what_gen_knows_comes_with_his_entry_and_stays_with_his_attachment(self) -> None:
        """ゲンがこの世界で知っていること (金庫の番号 1907) は、入るときの取り決めで渡り、ゲンの居場所が持つ。"""
        session = MineVillageSession().started()

        entry = session.casts.get(WORLD).entry_of(_GEN)
        attachment = session.beings.get(BeingId("gen")).attachment

        assert entry.known_facts is not None and "1907" in entry.known_facts
        assert attachment is not None and attachment.known_facts == entry.known_facts

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
        assert [d.heading for d in gen.orientation.descriptions] == ["世界の前提"]

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


class TestStartPlaySessionPreparesTurnRounds:
    """StartPlaySession が、コマンドの巡りの上限と待つ人を起こすまでの長さで巡りを作り、世界を開く前に置くことを保証する。"""

    def test_rounds_reach_the_round_limit_given_in_the_command(self) -> None:
        """巡りの上限 1 で始めると、置かれた巡りは 1 巡り閉じたところで上限に届く。"""
        session = MineVillageSession(round_limit=1).started()
        rounds = session.turn_rounds.get(WORLD)

        rounds.open_round({_GEN: FreeToAct()})
        rounds.finish_turn(_GEN, Acted())
        rounds.close_round()

        assert rounds.has_reached_round_limit() is True

    def test_rounds_wake_the_waiting_person_after_the_length_given_in_the_command(self) -> None:
        """起こすまでの長さ 1 で始めると、巡り 1 で待つを選んだゲンは巡り 2 を飛ばし、巡り 3 でターンが戻る。"""
        session = MineVillageSession(wake_waiting_after=1).started()
        rounds = session.turn_rounds.get(WORLD)
        due = []
        for outcome in (Waited(), None, None):
            rounds.open_round({_GEN: FreeToAct()})
            due.append(rounds.due_turns())
            if outcome is not None:
                rounds.finish_turn(_GEN, outcome)
            elif rounds.due_turns():
                rounds.finish_turn(_GEN, Acted())
            rounds.close_round()

        assert due == [(_GEN,), (), (_GEN,)]

    def test_rounds_are_in_place_before_the_world_opens(self) -> None:
        """世界を開く時点で、その世界の巡りがもう取り出せる。開くと入る人への観測が届き始めるため。"""
        found_when_opening: list[bool] = []

        def look_for_rounds() -> None:
            try:
                session.turn_rounds.get(WORLD)
                found_when_opening.append(True)
            except TurnRoundsNotFoundException:
                found_when_opening.append(False)

        session = MineVillageSession(on_opening_world=look_for_rounds)

        session.started()

        assert found_when_opening == [True]


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
