from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.eventing.domain_event import new_event_stamp
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator
from ai_rpg_world.game_world.domain.declaration.belongings_texts import BelongingsTexts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import UnfillableSceneTextException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.person_inventory import ItemGivenUpEvent, ItemReceivedEvent
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
from ai_rpg_world.game_world.domain.value_object import DisplayName, ItemSpecId, PersonId, WorldTick
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from tests.game_world.support.world_design_for_tests import belongings_texts

_GEN = PersonId("gen")


class TestBelongingsTexts:
    """BelongingsTexts が、持ち物の出入りを本人にだけ届く品物の名前つきの知らせにし、書けない言い回しを断ることを保証する。"""

    def test_received_item_is_told_only_to_the_person_by_name(self) -> None:
        """ゲンがカンテラの灯を受け取ると、ゲンだけに「カンテラの灯を入手した。」が届く知らせになる。"""
        told = belongings_texts().received_by(_GEN, DisplayName("カンテラの灯"), WorldTick(3))

        assert (told.audience, told.text.template.template, told.at) == (
            frozenset({_GEN}),
            "カンテラの灯を入手した。",
            WorldTick(3),
        )

    def test_given_up_item_is_told_only_to_the_person_by_name(self) -> None:
        """ゲンがカンテラの油を手放すと、ゲンだけに「カンテラの油を手放した。」が届く知らせになる。"""
        [told] = belongings_texts().given_up_by(_GEN, DisplayName("カンテラの油"), WorldTick(3), ran_out=False)

        assert (told.audience, told.text.template.template) == (frozenset({_GEN}), "カンテラの油を手放した。")

    def test_item_that_ran_out_is_not_told_as_given_up(self) -> None:
        """使い切って消えた品物 (燃え尽きた灯) は「手放した」と知らせない。尽きたことは品物の知らせが伝えるため。"""
        assert belongings_texts().given_up_by(_GEN, DisplayName("カンテラの灯"), WorldTick(16), ran_out=True) == ()

    def test_telling_does_not_push_aside_what_was_seen_or_heard(self) -> None:
        """持ち物の出入りの知らせは、同じときに見聞きした知らせを押しのけない (1 人に 1 つの数に入れない)。"""
        told = belongings_texts().received_by(_GEN, DisplayName("縄"), WorldTick(0))

        assert not told.counts_toward_one_per_person

    @pytest.mark.parametrize("text", ["何かを入手した。", "{item}を{who}から入手した。"])
    def test_wording_without_exactly_the_item_is_refused(self, text: str) -> None:
        """品物の名前を書かない言い回しや、品物の名前のほかに埋められない名前を書く言い回しは、UnfillableSceneTextException で断る。"""
        with pytest.raises(UnfillableSceneTextException):
            BelongingsTexts(received=TextWithUnassignedPeople(text), given_up=TextWithUnassignedPeople("{item}"))


class TestTranslatingBelongings:
    """StimulusTranslator が、持ち物のイベントを品物の名前と時刻つきの本人への知らせにし、使い切りは知らせないことを保証する。"""

    def test_received_event_becomes_a_notice_with_the_name_and_time(self, mine_village: WorldDesign) -> None:
        """ゲンがカンテラの灯を 3 tick 目に受け取ると、ゲンだけに 3 tick 目の「カンテラの灯を入手しました。」が届く知らせになる。"""
        event = ItemReceivedEvent(
            **new_event_stamp(),
            person=_GEN,
            item=ItemInstanceId("flame#1"),
            spec=ItemSpecId("lamp_flame"),
            at=WorldTick(3),
        )

        [told] = StimulusTranslator().stimuli_of(event, mine_village)

        assert isinstance(told, AnnouncementStimulus)
        assert (told.audience, told.text.template.template, told.at) == (
            frozenset({_GEN}),
            "カンテラの灯を入手しました。",
            WorldTick(3),
        )

    @pytest.mark.parametrize(("ran_out", "told"), [(False, ("カンテラの灯を捨てました。",)), (True, ())])
    def test_given_up_event_is_told_unless_it_ran_out(
        self, mine_village: WorldDesign, ran_out: bool, told: tuple[str, ...]
    ) -> None:
        """手放したカンテラの灯は「捨てました」と知らせ、燃え尽きて消えたときは何も知らせない。"""
        event = ItemGivenUpEvent(
            **new_event_stamp(),
            person=_GEN,
            item=ItemInstanceId("flame#1"),
            spec=ItemSpecId("lamp_flame"),
            was_held=True,
            ran_out=ran_out,
            at=WorldTick(16),
        )

        stimuli = StimulusTranslator().stimuli_of(event, mine_village)

        assert tuple(s.text.template.template for s in stimuli if isinstance(s, AnnouncementStimulus)) == told
        assert len(stimuli) == len(told)


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(Path(__file__).parents[4] / "data" / "scenarios" / "mine_village_v2.yaml").design
