from __future__ import annotations

from ai_rpg_world.game_world.domain.perception import Background, Notable
from ai_rpg_world.game_world.domain.perception.bodily_stimulus import BodilyStimulus
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, VIEW, about, awake, departed, fallen


def _cold_on(person=ALICE) -> BodilyStimulus:
    return BodilyStimulus(
        person=person, text=about("{me}は寒さに震えた", me=person), salience=Notable(), at=WorldTick(4)
    )


class TestBodilyStimulusPerceivedBy:
    """BodilyStimulus.perceived_by が、体の刺激を本人だけに、倒れていても届け、去った人には届けないことを保証する。"""

    def test_the_person_feels_it_with_the_text_seen_by_them(self) -> None:
        """起きている本人には、文に view で呼び方を当て、Felt と刺激の時刻を付けて届く。"""
        outcome = _cold_on().perceived_by(awake(ALICE), VIEW)

        assert outcome == Perceived(
            perceiver=ALICE,
            text=about("{me}は寒さに震えた", me=ALICE).seen_by(VIEW),
            quality=Felt(),
            happened_at=WorldTick(4),
            calls_attention=True,
        )

    def test_someone_else_does_not_feel_it(self) -> None:
        """本人でない人には NotPerceived を返す。"""
        assert _cold_on().perceived_by(awake(BOB), VIEW) == NotPerceived()

    def test_a_fallen_person_still_feels_it(self) -> None:
        """倒れている本人にも、気を失っていても体に残るので Felt で届く。"""
        outcome = _cold_on().perceived_by(fallen(ALICE), VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == Felt()

    def test_a_departed_person_has_no_body_to_feel_it(self) -> None:
        """去った人には体が無いので、本人であっても NotPerceived を返す。"""
        assert _cold_on().perceived_by(departed(ALICE), VIEW) == NotPerceived()

    def test_a_background_feeling_does_not_call_attention(self) -> None:
        """Background の体の刺激は、本人が感じても calls_attention は偽。"""
        stimulus = BodilyStimulus(
            person=ALICE, text=about("{me}は鍵を拾った", me=ALICE), salience=Background(), at=WorldTick(4)
        )

        outcome = stimulus.perceived_by(awake(ALICE), VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.calls_attention is False
