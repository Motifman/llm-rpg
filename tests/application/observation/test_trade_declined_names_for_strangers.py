"""取引を断られた観測を出品者の記録に入れるとき、名前を知らない断った人が見た目で書かれることを保証する (#1609)。

formatter が組んだ観測を ``PlayerAcquaintances.view_for`` に通し、受け手の記録に入る版を見る。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.trade_formatter import (
    TradeObservationFormatter,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import TradeDeclinedEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId

SELLER = PlayerId(1)
DECLINER = PlayerId(2)
NAMES = {1: "ハル", 2: "サヨ"}
LOOKS = {1: "測量具を背負った年かさの人", 2: "綿入れを着込んだ若い娘"}


def _formatter() -> TradeObservationFormatter:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.player_name.side_effect = lambda pid: NAMES[pid.value]
    return TradeObservationFormatter(ObservationFormatterContext(name_resolver=name_resolver, item_repository=None))


def _acquaintances() -> PlayerAcquaintances:
    """ハルはサヨに会ったが、まだ名前を知らない。"""
    acquaintances = PlayerAcquaintances(
        store=InMemoryAcquaintanceRepository(),
        being_id_of=lambda pid: BeingId(f"being_p{pid.value}"),
        turn_reader=InMemoryMemoryTurnClock(),
        environment_name="山村",
        names_by_player_id=NAMES,
        appearances_by_player_id=LOOKS,
    )
    acquaintances.record_meeting(SELLER, "サヨ")
    return acquaintances


def _recorded_by_seller(acquaintances: PlayerAcquaintances) -> ObservationOutput:
    event = TradeDeclinedEvent.create(
        aggregate_id=TradeId(1),
        aggregate_type="TradeAggregate",
        decliner_id=DECLINER,
    )
    output = _formatter().format(event, SELLER)
    assert output is not None
    chosen = acquaintances.view_for(SELLER, output)
    assert chosen is not None
    return chosen


class TestTradeDeclinedSeenByTheSeller:
    """取引を断られた観測で、出品者が断った人を呼ぶ言葉を保証する。"""

    def test_decliner_whose_name_is_unknown_is_written_by_appearance(self) -> None:
        """名前を知らない人に断られると、出品者の記録には見た目で書かれ、名前は本文にも structured にも出ない。"""
        acquaintances = _acquaintances()

        chosen = _recorded_by_seller(acquaintances)

        assert chosen.prose == "綿入れを着込んだ若い娘が取引を断りました。"
        assert "サヨ" not in str(chosen.structured)

    def test_decliner_whose_name_is_known_is_written_by_name(self) -> None:
        """名前を知っている人に断られると、出品者の記録には名前のまま書かれる。"""
        acquaintances = _acquaintances()
        acquaintances.learn_name(SELLER, DECLINER, how="名乗り")

        chosen = _recorded_by_seller(acquaintances)

        assert chosen.prose == "サヨが取引を断りました。"
