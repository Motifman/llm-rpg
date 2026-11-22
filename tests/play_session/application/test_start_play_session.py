from __future__ import annotations

from ai_rpg_world.being.contract import Introduction
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.domain.value_object import PersonId
from tests.play_session.mine_village_session import ENVIRONMENT_NAME, WORLD, MineVillageSession

_GEN = PersonId("gen")


class TestStartPlaySession:
    """StartPlaySession が、廃坑の山村 v2 を開き、4 人の Being を人柄から用意して、入るときの材料を渡して入れることを保証する。"""

    def test_gen_is_prepared_with_name_and_first_person_from_the_scenario(self) -> None:
        """ゲンの Being は、シナリオの人柄どおり名前「ゲン」と一人称「俺」で用意される。"""
        session = MineVillageSession()

        persona = session.beings.get(BeingId("gen")).persona

        assert (persona.name, persona.first_person) == ("ゲン", "俺")

    def test_every_being_enters_the_world(self) -> None:
        """4 人の Being がどれも、世界の識別子と環境の名前「廃坑の山村」の環境に入っている。"""
        session = MineVillageSession()

        attachments = {being: session.beings.get(BeingId(being)).attachment for being in ("gen", "sayo", "haru", "mio")}

        assert set(attachments.values()) == {
            BeingAttachment(environment_id=WORLD.value, environment_name=ENVIRONMENT_NAME)
        }

    def test_gens_orientation_has_introduction_premises_and_what_he_knows(self) -> None:
        """ゲンの案内には導入・前提・「あなたが知っていること」が並び、知っていることに金庫の番号 1907 がある。"""
        session = MineVillageSession()

        descriptions = tuple(session.casts.get(WORLD).orientation_of(_GEN).descriptions)

        assert [d.heading for d in descriptions] == ["この世界について", "この世界の前提", "あなたが知っていること"]
        assert "1907" in descriptions[2].text

    def test_gens_imposed_goal_is_only_his_objective(self) -> None:
        """ゲンに課された目的は「サヨと二人そろって、坑道の奥の昇降機で外へ出る。」だけになる。"""
        session = MineVillageSession()

        entry = session.casts.get(WORLD).entry_of(_GEN)

        assert entry.imposed_goal == "サヨと二人そろって、坑道の奥の昇降機で外へ出る。"

    def test_gen_is_introduced_to_sayo_only(self) -> None:
        """ゲンの紹介にはサヨだけが入り、ハルとミオは入らない。ゲンの知り合いにもサヨだけが記録される。"""
        session = MineVillageSession()

        entry = session.casts.get(WORLD).entry_of(_GEN)
        known = [a.name for a in session.acquaintances.list_by_being(BeingId("gen"))]

        assert tuple(entry.introductions) == (Introduction(name="サヨ"),)
        assert known == ["サヨ"]

    def test_entry_and_orientation_given_to_each_being_are_announced(self) -> None:
        """4 人それぞれに、渡した取り決めと案内を持つ BeingCastInWorldEvent が 1 件ずつ出る。"""
        session = MineVillageSession()
        cast = session.casts.get(WORLD)

        announced = {event.person: (event.being_id, event.entry, event.orientation) for event in session.cast_events}

        assert len(session.cast_events) == 4
        assert announced[_GEN] == (BeingId("gen"), cast.entry_of(_GEN), cast.orientation_of(_GEN))
