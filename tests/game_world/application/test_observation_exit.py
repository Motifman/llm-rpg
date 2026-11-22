from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from ai_rpg_world.being.contract import (
    UNKNOWN,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnBodyState,
    PersonInText,
    SeenOrHeard,
    TextWithPeople,
    UnidentifiedPerson,
)
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception import Perceived
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt, NoticedOnWaking, PerceivedQuality, Told
from ai_rpg_world.game_world.domain.sound import HearsClearly, HearsFaintly, HearsMuffled
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from tests.game_world.support.world_design_for_tests import clock_wording, half_hour_ticks_from_midnight

_WORLD = WorldId("exit_world")
_MINE_VILLAGE_V2 = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_ALICE = PersonId("alice")
_KAI = PersonRef(handle=PersonHandle(2), appearance=DescriptionText("日に焼けた若者"), visible_name=DisplayName("カイ"))
_STRANGER = PersonRef(handle=PersonHandle(5), appearance=DescriptionText("背の高い男"), visible_name=NoVisibleName())


class _Received:
    def __init__(self) -> None:
        self.observations: list[tuple[PersonId, Observation]] = []

    def receive(self, person: PersonId, observation: Observation) -> None:
        self.observations.append((person, observation))


def _perceived(
    text: TextWithAssignedPeople | None = None,
    *,
    quality: PerceivedQuality = SeesClearly(),
    at: int = 12,
    calls_attention: bool = True,
) -> Perceived:
    return Perceived(
        perceiver=_ALICE,
        text=text if text is not None else TextWithAssignedPeople(template="扉が開いた", people={}),
        quality=quality,
        happened_at=WorldTick(at),
        calls_attention=calls_attention,
    )


def _handed_over(perceived: Perceived) -> tuple[PersonId, Observation]:
    received = _Received()

    ObservationExit(_WORLD, half_hour_ticks_from_midnight(), clock_wording(), received).hand_over(perceived)

    assert len(received.observations) == 1
    return received.observations[0]


class TestObservationExit:
    """ObservationExit.hand_over が、知覚した結果を、時刻の札を付けた Being の契約の観測にして、知覚した人の受け口へ渡すことを保証する。"""

    def test_observation_goes_to_the_perceiver(self) -> None:
        """観測は、知覚した人 (perceiver) の宛先で受け口に渡る。"""
        person, _ = _handed_over(_perceived())

        assert person == _ALICE

    def test_observation_carries_the_day_and_clock_time_as_its_time_and_the_tick_as_its_order(self) -> None:
        """1 日 48 tick、始まり 00:00 の世界で 61 tick に起きたことの観測は、時刻の札「Day 2 6:30」と、この世界の中で 61 番目に起きた順を持つ。"""
        _, observation = _handed_over(_perceived(at=61))

        assert observation.time == ObservedTime(display="Day 2 6:30")
        assert observation.order == OccurrenceOrder(environment="exit_world", value=61)

    def test_people_in_the_text_become_people_marks_of_the_contract(self) -> None:
        """名前の見える人は名前つき、見えない人は名前なし、見分けのつかない人は UnidentifiedPerson の印になり、文のプレースホルダーはそのまま残る。"""
        text = TextWithAssignedPeople(
            template="{actor}が{target}に何かを渡し、{someone}が見ていた",
            people={"actor": _KAI, "target": _STRANGER, "someone": Unidentified()},
        )

        _, observation = _handed_over(_perceived(text))

        assert observation.body == TextWithPeople(
            template="{actor}が{target}に何かを渡し、{someone}が見ていた",
            people={
                "actor": PersonInText(handle=2, appearance="日に焼けた若者", visible_name="カイ"),
                "target": PersonInText(handle=5, appearance="背の高い男", visible_name=None),
                "someone": UnidentifiedPerson(),
            },
        )

    @pytest.mark.parametrize(
        ("quality", "route"),
        [
            (SeesClearly(), SeenOrHeard()),
            (SeesShapes(), SeenOrHeard()),
            (HearsClearly(), SeenOrHeard()),
            (HearsMuffled(), SeenOrHeard()),
            (HearsFaintly(), SeenOrHeard()),
            (Felt(), OwnBodyState()),
            (Told(), EnvironmentNotice()),
            (NoticedOnWaking(), EnvironmentNotice()),
        ],
    )
    def test_route_follows_how_it_was_perceived(self, quality: PerceivedQuality, route: object) -> None:
        """見た・聞いたものは「見た・聞いた」、体で感じたものは「自分の体の状態」、知らされたものは「環境からの知らせ」の経路になる。"""
        _, observation = _handed_over(_perceived(quality=quality))

        assert observation.route == route

    @pytest.mark.parametrize("quality", [kind() for kind in get_args(PerceivedQuality)])
    def test_every_kind_of_perceived_quality_has_a_route(self, quality: PerceivedQuality) -> None:
        """知覚の質のどの種類にも、観測の経路が決まっている。"""
        _, observation = _handed_over(_perceived(quality=quality))

        assert observation.route in (SeenOrHeard(), OwnBodyState(), EnvironmentNotice())

    @pytest.mark.parametrize("calls_attention", [True, False])
    def test_wants_wake_follows_whether_it_calls_attention(self, calls_attention: bool) -> None:
        """考え直す目安 (calls_attention) が、そのまま起こしたいかの助言 (wants_wake) になる。"""
        _, observation = _handed_over(_perceived(calls_attention=calls_attention))

        assert observation.wants_wake is calls_attention

    def test_what_the_perception_does_not_know_is_unknown(self) -> None:
        """主体が本人かは偽、主体の名前・出どころ・場所・自分宛てかは「不明」になる。"""
        _, observation = _handed_over(_perceived())

        assert observation.subject_is_self is False
        assert observation.unknown_fields() == ("subject_name", "source", "place", "addressed_to_self")
        assert observation.subject_name is UNKNOWN


class TestObservationExitInMineVillageV2:
    """廃坑の山村 v2 の昼夜の宣言を渡した観測の出口が、観測の時刻を何日目と時:分で出すことを保証する。"""

    def test_safe_opened_at_tick_61_is_seen_at_day_two_six_thirty(self) -> None:
        """1 日 48 tick、始まり 00:00 の廃坑の山村 v2 で 61 tick に起きたことの観測は、時刻の札「Day 2 6:30」を持つ。"""
        day_night = load_scenario(_MINE_VILLAGE_V2).design.day_night
        assert isinstance(day_night, DayNightDeclaration)
        received = _Received()

        ObservationExit(_WORLD, day_night, clock_wording(), received).hand_over(_perceived(at=61))

        [(_, observation)] = received.observations
        assert observation.time == ObservedTime(display="Day 2 6:30")
