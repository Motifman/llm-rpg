import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.pursuit.event import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def build_snapshot() -> PursuitTargetSnapshot:
    return PursuitTargetSnapshot(
        target_id=WorldObjectId(22),
        spot_id=SpotId(7),
        coordinate=Coordinate(12, 4, 0),
    )


def build_last_known() -> PursuitLastKnownState:
    return PursuitLastKnownState(
        target_id=WorldObjectId(22),
        spot_id=SpotId(7),
        coordinate=Coordinate(12, 4, 0),
        observed_at_tick=WorldTick(30),
    )


class TestPursuitEvents:
    def test_create_started_event(self):
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            target_snapshot=build_snapshot(),
            last_known=build_last_known(),
        )

        assert event.actor_id == WorldObjectId(11)
        assert event.target_id == WorldObjectId(22)
        assert event.target_snapshot == build_snapshot()
        assert event.last_known == build_last_known()
        assert event.last_known.observed_at_tick == WorldTick(30)

    def test_create_updated_event(self):
        event = PursuitUpdatedEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            last_known=build_last_known(),
            target_snapshot=build_snapshot(),
        )

        assert event.actor_id == WorldObjectId(11)
        assert event.target_id == WorldObjectId(22)
        assert event.last_known == build_last_known()
        assert event.target_snapshot == build_snapshot()
        assert event.last_known.observed_at_tick == WorldTick(30)

    def test_create_failed_event(self):
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
            last_known=build_last_known(),
            target_snapshot=build_snapshot(),
        )

        assert event.failure_reason == PursuitFailureReason.PATH_UNREACHABLE
        assert event.actor_id == WorldObjectId(11)
        assert event.target_id == WorldObjectId(22)
        assert event.last_known == build_last_known()
        assert event.target_snapshot == build_snapshot()

    def test_create_cancelled_event(self):
        event = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            last_known=build_last_known(),
            target_snapshot=build_snapshot(),
        )

        assert event.actor_id == WorldObjectId(11)
        assert event.target_id == WorldObjectId(22)
        assert event.last_known == build_last_known()
        assert event.target_snapshot == build_snapshot()

    def test_cancelled_event_is_distinct_from_failure_event(self):
        cancelled = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            last_known=build_last_known(),
        )
        failed = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            actor_id=WorldObjectId(11),
            target_id=WorldObjectId(22),
            failure_reason=PursuitFailureReason.TARGET_MISSING,
            last_known=build_last_known(),
        )

        assert not hasattr(cancelled, "failure_reason")
        assert failed.failure_reason == PursuitFailureReason.TARGET_MISSING
        assert cancelled.actor_id == failed.actor_id
        assert cancelled.target_id == failed.target_id

    def test_failure_reason_values_exclude_cancelled(self):
        values = {reason.value for reason in PursuitFailureReason}

        assert "cancelled" not in values

    @pytest.mark.parametrize(
        ("event_cls", "expected_snapshot"),
        [
            (PursuitStartedEvent, True),
            (PursuitUpdatedEvent, True),
            (PursuitFailedEvent, True),
            (PursuitCancelledEvent, True),
        ],
    )
    def test_event_payloads_include_downstream_context(
        self,
        event_cls,
        expected_snapshot,
    ):
        kwargs = {
            "actor_id": WorldObjectId(11),
            "target_id": WorldObjectId(22),
            "last_known": build_last_known(),
            "target_snapshot": build_snapshot(),
        }
        if event_cls is PursuitFailedEvent:
            kwargs["failure_reason"] = (
                PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
            )
        event = event_cls.create(
            aggregate_id=WorldObjectId(11),
            aggregate_type="Actor",
            **kwargs,
        )

        assert event.aggregate_id == WorldObjectId(11)
        assert event.aggregate_type == "Actor"
        assert event.actor_id == WorldObjectId(11)
        assert event.target_id == WorldObjectId(22)
        assert event.last_known.spot_id == SpotId(7)
        assert event.last_known.coordinate == Coordinate(12, 4, 0)
        assert event.last_known.observed_at_tick == WorldTick(30)
        if expected_snapshot:
            assert event.target_snapshot is not None
            assert event.target_snapshot.spot_id == SpotId(7)
            assert event.target_snapshot.coordinate == Coordinate(12, 4, 0)
