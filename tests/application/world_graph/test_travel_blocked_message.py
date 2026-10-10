"""travel_blocked_cue が、閉じた通路の種類と状態・通行条件の文から手がかりの 1 文を作ることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotTravelBlocked,
    SpotTravelBlockedReason,
)
from ai_rpg_world.application.world_graph.travel_blocked_message import travel_blocked_cue
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId


def _blocked(
    *,
    kind: str = "DOOR",
    state: str = "LOCKED",
    reason: SpotTravelBlockedReason = SpotTravelBlockedReason.PASSAGE_CLOSED,
    condition_message: str | None = None,
) -> SpotTravelBlocked:
    return SpotTravelBlocked(
        connection_id=ConnectionId.create(1),
        connection_name="北の扉",
        from_spot_id=SpotId.create(1),
        to_spot_id=SpotId.create(2),
        destination_spot_id=SpotId.create(2),
        passage_kind=kind,
        passage_state=state,
        reason=reason,
        condition_message=condition_message,
    )


@pytest.mark.parametrize(
    ("kind", "state", "expected"),
    [
        ("DOOR", "LOCKED", "北の扉は閉ざされていて、開かない。その先へは行けない。"),
        ("DOOR", "CLOSED", "北の扉は閉ざされていて、開かない。その先へは行けない。"),
        ("WALL", "INTACT", "北の扉は壁に阻まれている。その先へは行けない。"),
        ("BARRIER", "ACTIVE", "北の扉は塞がっていて、通れない。その先へは行けない。"),
        ("OPEN", "OPEN", "北の扉は通れなくなっている。その先へは行けない。"),
    ],
)
def test_closed_passage_cue_depends_on_passage_kind(kind, state, expected) -> None:
    """通路が閉じて止まったとき、手がかりの文は通路の種類で決まり、通路の名前で始まる。"""
    assert travel_blocked_cue(_blocked(kind=kind, state=state)) == expected


def test_condition_cue_uses_the_scenario_message_and_adds_a_period() -> None:
    """通行条件で止まったとき、シナリオの文に句点が無ければ足してから「その先へは行けない。」を続ける。"""
    blocked = _blocked(
        kind="OPEN",
        state="OPEN",
        reason=SpotTravelBlockedReason.PASSAGE_CONDITION,
        condition_message="吊り橋が上がっている",
    )

    assert travel_blocked_cue(blocked) == "吊り橋が上がっている。その先へは行けない。"


def test_condition_cue_without_message_is_only_the_plain_sentence() -> None:
    """通行条件で止まり、シナリオの文が空のときは「その先へは行けない。」だけになる。"""
    blocked = _blocked(
        reason=SpotTravelBlockedReason.PASSAGE_CONDITION,
        condition_message="  ",
    )

    assert travel_blocked_cue(blocked) == "その先へは行けない。"
