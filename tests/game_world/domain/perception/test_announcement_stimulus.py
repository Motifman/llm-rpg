from __future__ import annotations

from ai_rpg_world.game_world.domain.perception import Background, Notable
from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perceived_quality import Told
from ai_rpg_world.game_world.domain.perception.perception_outcome import NoticedLater, NotPerceived, Perceived
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, CAROL, HALL, VIEW, about, awake, departed, fallen

_TEXT = about("{caller}が皆を広間へ呼び集めている", caller=CAROL)


def _call_to(*audience) -> AnnouncementStimulus:
    return AnnouncementStimulus(audience=frozenset(audience), text=_TEXT, salience=Notable(), at=WorldTick(7))


class TestAnnouncementStimulusPerceivedBy:
    """AnnouncementStimulus.perceived_by が、選ばれた人にだけ、居場所に関わらず知らせを届けることを保証する。"""

    def test_someone_in_the_audience_is_told_wherever_they_are(self) -> None:
        """audience にいる起きている人には、別の場所にいても、view で呼び方を当てた文が Told で届く。"""
        outcome = _call_to(ALICE).perceived_by(awake(ALICE, HALL), VIEW)

        assert outcome == Perceived(
            perceiver=ALICE, text=_TEXT.seen_by(VIEW), quality=Told(), happened_at=WorldTick(7), calls_attention=True
        )

    def test_someone_outside_the_audience_is_not_told(self) -> None:
        """audience にいない人には NotPerceived を返す。"""
        assert _call_to(ALICE).perceived_by(awake(BOB), VIEW) == NotPerceived()

    def test_a_fallen_person_in_the_audience_notices_it_later(self) -> None:
        """audience にいる倒れている人には、知らせの文をそのまま MissedNotice にして NoticedLater で返す。"""
        outcome = _call_to(ALICE).perceived_by(fallen(ALICE), VIEW)

        assert outcome == NoticedLater(notice=MissedNotice(text=_TEXT.seen_by(VIEW), happened_at=WorldTick(7)))

    def test_a_departed_person_in_the_audience_is_told(self) -> None:
        """audience にいる去った人にも Told で届く。"""
        outcome = _call_to(ALICE).perceived_by(departed(ALICE), VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == Told()

    def test_a_background_announcement_does_not_call_attention(self) -> None:
        """Background の知らせは、宛てられた本人に届いても calls_attention は偽。"""
        stimulus = AnnouncementStimulus(audience=frozenset({ALICE}), text=_TEXT, salience=Background(), at=WorldTick(7))

        outcome = stimulus.perceived_by(awake(ALICE), VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.calls_attention is False
