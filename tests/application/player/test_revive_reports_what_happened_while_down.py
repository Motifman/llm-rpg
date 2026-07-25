"""意識を取り戻したとき、倒れていた間に自分が何をされたかを知れる。

倒れている player は observation の宛先から一律に外れる (Issue #621 Phase 4:
ターンが回らず観測を消化できないため)。一方で、奪う (take) が成立するのは
**倒れている相手だけ** である。つまり被害者は構造的に、自分が何をされたのかを
観測できない。

気を失っている間の出来事を「その瞬間に」知覚しないのは筋が通る。しかし起きた
あとも永久に分からないままだと、荷が減った理由が誰にも説明できない。目を覚ま
した本人が「持ち物を漁られた形跡がある」と気付けるところまでが必要である。

そこで、倒れている間に自分を対象として行われた行為を記録しておき、復活時の
post hoc summary (Issue #621 Phase 5) に併せて渡す。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.player.handlers.player_revived_post_hoc_observation_handler import (
    PlayerRevivedPostHocObservationHandler,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.application.player.services.downed_incident_log import (
    DownedIncidentLog,
)
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_VICTIM = PlayerId(2)


def _event() -> PlayerRevivedEvent:
    return PlayerRevivedEvent.create(
        aggregate_id=_VICTIM,
        aggregate_type="PlayerStatusAggregate",
        hp_recovered=40,
        total_hp=40,
        caregiver_player_id=PlayerId(1),
    )


def _handler(log: DownedIncidentLog | None) -> tuple:
    timer = PlayerDeathGraceTimer()
    timer.register(_VICTIM, downed_at_tick=10)
    appender = MagicMock()
    handler = PlayerRevivedPostHocObservationHandler(
        grace_timer=timer,
        observation_appender=appender,
        current_tick_provider=lambda: 18,
        caregiver_name_resolver=lambda pid: {1: "ハル"}.get(int(pid)),
        downed_incident_log=log,
    )
    return handler, appender


def _prose(appender) -> str:
    return appender.append.call_args.kwargs["output"].prose


class TestReviveReportsIncidents:
    """倒れていた間に自分を対象として行われた行為が、復活時に伝わる。"""

    def test_recorded_incident_appears_in_the_wake_up_summary(self) -> None:
        """記録された行為が、目覚めの観測文に含まれる。"""
        log = DownedIncidentLog()
        log.record(_VICTIM, "リンに持ち物を奪われた")
        handler, appender = _handler(log)

        handler.handle(_event())

        assert "リンに持ち物を奪われた" in _prose(appender)

    def test_multiple_incidents_are_all_reported(self) -> None:
        """複数回やられていれば、すべて伝わる。

        1 件だけ伝えると「他にも何かされたかもしれない」が残り、荷の増減を
        説明できない。
        """
        log = DownedIncidentLog()
        log.record(_VICTIM, "リンに持ち物を奪われた")
        log.record(_VICTIM, "カイトに印を刻まれた")
        handler, appender = _handler(log)

        handler.handle(_event())

        prose = _prose(appender)
        assert "リンに持ち物を奪われた" in prose
        assert "カイトに印を刻まれた" in prose

    def test_nothing_happened_adds_nothing(self) -> None:
        """何もされていなければ、余計な文を足さない。"""
        handler, appender = _handler(DownedIncidentLog())

        handler.handle(_event())

        prose = _prose(appender)
        assert "意識が戻った" in prose
        assert "形跡" not in prose

    def test_incidents_are_consumed_so_they_are_not_replayed(self) -> None:
        """一度伝えた行為は、次に倒れて起きたときに繰り返さない。

        drain しないと、2 度目の復活で 1 度目の被害まで再び読まされる。
        """
        log = DownedIncidentLog()
        log.record(_VICTIM, "リンに持ち物を奪われた")
        handler, appender = _handler(log)

        handler.handle(_event())
        handler.handle(_event())

        assert "リンに持ち物を奪われた" not in _prose(appender)

    def test_log_is_per_player(self) -> None:
        """他人が受けた行為は混ざらない。"""
        log = DownedIncidentLog()
        log.record(PlayerId(3), "別人が奪われた")
        handler, appender = _handler(log)

        handler.handle(_event())

        assert "別人が奪われた" not in _prose(appender)

    def test_handler_works_without_a_log(self) -> None:
        """log を注入しない構成でも、従来どおりの目覚め文を返す。

        既存の呼び出し元 (テスト / 旧構成) を壊さない。
        """
        handler, appender = _handler(None)

        handler.handle(_event())

        assert "意識が戻った" in _prose(appender)
