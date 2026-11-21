from __future__ import annotations

from ai_rpg_world.game_world.domain.lighting import SeesClearly
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perception_outcome import NoticedLater, NotPerceived, Perceived
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, VIEW, about


class _Recipient:
    def __init__(self) -> None:
        self.handed: list[tuple[str, object]] = []

    def perceived(self, perceived: Perceived) -> None:
        self.handed.append(("perceived", perceived))

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self.handed.append(("noticed_later", (perceiver, notice)))

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        self.handed.append(("not_perceived", (perceiver, reason)))


class TestHandOver:
    """知覚の結果の hand_over が、届いたものだけを、届き方に合った受け口へ渡すことを保証する。"""

    def test_perceived_is_handed_as_perceived(self) -> None:
        """Perceived は、そのまま受け手の perceived に渡る。"""
        perceived = Perceived(
            perceiver=ALICE,
            text=about("扉が開いた").seen_by(VIEW),
            quality=SeesClearly(),
            happened_at=WorldTick(3),
            calls_attention=False,
        )
        recipient = _Recipient()

        perceived.hand_over(ALICE, recipient)

        assert recipient.handed == [("perceived", perceived)]

    def test_noticed_later_is_handed_with_the_perceiver(self) -> None:
        """NoticedLater は、知覚した人と一緒に、ためておく知らせとして受け手の noticed_later に渡る。"""
        notice = MissedNotice(text=about("荷が軽くなっている").seen_by(VIEW), happened_at=WorldTick(3))
        recipient = _Recipient()

        NoticedLater(notice=notice).hand_over(BOB, recipient)

        assert recipient.handed == [("noticed_later", (BOB, notice))]

    def test_not_perceived_is_handed_with_its_reason(self) -> None:
        """NotPerceived は、知覚しなかった人と理由を、受け手の not_perceived に渡す。"""
        recipient = _Recipient()

        NotPerceived(NotPerceivedReason.TOO_DARK).hand_over(ALICE, recipient)

        assert recipient.handed == [("not_perceived", (ALICE, NotPerceivedReason.TOO_DARK))]
