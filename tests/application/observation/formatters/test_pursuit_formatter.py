"""PursuitObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.pursuit_formatter import (
    PursuitObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.world.event.map_events import LocationEnteredEvent
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


def _make_context() -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=None,
        item_repository=None,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


def _build_pursuit_snapshot(target_id_value: int = 2, spot_id_value: int = 20) -> PursuitTargetSnapshot:
    return PursuitTargetSnapshot(
        target_id=WorldObjectId(target_id_value),
        spot_id=SpotId(spot_id_value),
        coordinate=Coordinate(5, 6, 0),
    )


def _build_pursuit_last_known(
    target_id_value: int = 2,
    spot_id_value: int = 21,
    observed_at_tick_value: int | None = 42,
) -> PursuitLastKnownState:
    return PursuitLastKnownState(
        target_id=WorldObjectId(target_id_value),
        spot_id=SpotId(spot_id_value),
        coordinate=Coordinate(7, 8, 0),
        observed_at_tick=WorldTick(observed_at_tick_value) if observed_at_tick_value is not None else None,
    )


class TestPursuitObservationFormatterCreation:
    """PursuitObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる。"""
        ctx = _make_context()
        formatter = PursuitObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = PursuitObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestPursuitObservationFormatterPursuitStarted:
    """PursuitStartedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """追跡開始は prose と structured を返す。"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "追跡を開始" in out.prose
        assert out.prose == "対象の追跡を開始しました。"
        assert out.structured["event_type"] == "pursuit_started"
        assert out.structured["pursuit_status_after_event"] == "active"
        assert out.observation_category == "self_only"

    def test_includes_actor_and_target_ids(self, formatter):
        """actor_id と target_id が structured に含まれる。"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(10),
            target_id=WorldObjectId(20),
            target_snapshot=_build_pursuit_snapshot(20),
            last_known=_build_pursuit_last_known(20),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["actor_id"] == 10
        assert out.structured["target_id"] == 20
        assert out.structured["actor_world_object_id"] == 10
        assert out.structured["target_world_object_id"] == 20

    def test_includes_last_known_and_target_snapshot_metadata(self, formatter):
        """last_known と target_snapshot が正しくシリアライズされる。"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(2, 20),
            last_known=_build_pursuit_last_known(2, 21, 42),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["spot_id_value"] == 21
        assert out.structured["last_known"] == {
            "target_id": 2,
            "spot_id_value": 21,
            "coordinate": {"x": 7, "y": 8, "z": 0},
            "observed_at_tick": 42,
        }
        assert out.structured["target_snapshot"] == {
            "target_id": 2,
            "spot_id_value": 20,
            "coordinate": {"x": 5, "y": 6, "z": 0},
        }

    def test_observation_category_is_self_only(self, formatter):
        """観測カテゴリは self_only。"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.observation_category == "self_only"

    def test_schedules_turn_and_breaks_movement_defaults(self, formatter):
        """PursuitStarted は schedules_turn/breaks_movement のデフォルト（False）。"""
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is False
        assert out.breaks_movement is False


class TestPursuitObservationFormatterPursuitUpdated:
    """PursuitUpdatedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """追跡更新は prose と structured を返す。"""
        event = PursuitUpdatedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "追跡状況を更新" in out.prose
        assert out.prose == "対象の追跡状況を更新しました。"
        assert out.structured["event_type"] == "pursuit_updated"
        assert out.structured["pursuit_status_after_event"] == "active"

    def test_without_target_snapshot_omits_snapshot_metadata(self, formatter):
        """target_snapshot が None のとき target_snapshot は None。"""
        event = PursuitUpdatedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=None,
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["target_snapshot"] is None
        assert out.structured["last_known"] is not None
        assert out.structured["spot_id_value"] == 21


class TestPursuitObservationFormatterPursuitFailed:
    """PursuitFailedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """追跡失敗は prose と structured を返す。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "追跡に失敗" in out.prose
        assert out.prose == "追跡に失敗しました。"
        assert out.structured["event_type"] == "pursuit_failed"
        assert out.structured["pursuit_status_after_event"] == "ended"
        assert out.structured["interruption_scope"] == "pursuit"

    def test_includes_failure_reason_target_missing(self, formatter):
        """TARGET_MISSING が failure_reason に含まれる。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.TARGET_MISSING,
            target_snapshot=None,
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["failure_reason"] == "target_missing"
        assert out.structured["target_snapshot"] is None

    def test_includes_failure_reason_path_unreachable(self, formatter):
        """PATH_UNREACHABLE が failure_reason に含まれる。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["failure_reason"] == "path_unreachable"

    def test_includes_failure_reason_vision_lost_at_last_known(self, formatter):
        """VISION_LOST_AT_LAST_KNOWN が failure_reason に含まれる。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN,
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["failure_reason"] == "vision_lost_at_last_known"

    def test_schedules_turn_true_breaks_movement_false(self, formatter):
        """PursuitFailed は schedules_turn=True, breaks_movement=False。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True
        assert out.breaks_movement is False

    def test_omits_target_snapshot_when_missing(self, formatter):
        """target_snapshot が None のとき target_snapshot は None。"""
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.TARGET_MISSING,
            target_snapshot=None,
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["target_snapshot"] is None
        assert out.structured["last_known"] == {
            "target_id": 2,
            "spot_id_value": 21,
            "coordinate": {"x": 7, "y": 8, "z": 0},
            "observed_at_tick": 42,
        }


class TestPursuitObservationFormatterPursuitCancelled:
    """PursuitCancelledEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """追跡中断は prose と structured を返す。"""
        event = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "追跡を中断" in out.prose
        assert out.prose == "追跡を中断しました。"
        assert out.structured["event_type"] == "pursuit_cancelled"
        assert out.structured["pursuit_status_after_event"] == "ended"
        assert out.structured["interruption_scope"] == "pursuit"

    def test_schedules_turn_true_breaks_movement_false(self, formatter):
        """PursuitCancelled は schedules_turn=True, breaks_movement=False。"""
        event = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True
        assert out.breaks_movement is False

    def test_without_target_snapshot_omits_snapshot_metadata(self, formatter):
        """target_snapshot が None のとき target_snapshot は None。"""
        event = PursuitCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=None,
            last_known=_build_pursuit_last_known(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured["target_snapshot"] is None


class TestPursuitObservationFormatterSerialization:
    """シリアライズの境界・異常系テスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_last_known_without_observed_at_tick(self, formatter):
        """observed_at_tick が None のときもシリアライズできる。"""
        last_known = _build_pursuit_last_known(observed_at_tick_value=None)
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=last_known,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "last_known" in out.structured
        assert "observed_at_tick" in out.structured["last_known"]


class TestPursuitObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return PursuitObservationFormatter(_make_context())

    def test_returns_none_for_player_location_changed(self, formatter):
        """PlayerLocationChangedEvent は None。"""
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_returns_none_for_location_entered(self, formatter):
        """LocationEnteredEvent は None。"""
        loc_id = LocationAreaId(1)
        event = LocationEnteredEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            name="町の広場",
            description="",
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_returns_none_for_random_object(self, formatter):
        """任意のオブジェクトは None。"""
        out = formatter.format({"type": "unknown"}, PlayerId(1))
        assert out is None

    def test_returns_none_for_none_event(self, formatter):
        """None イベントは None。"""
        out = formatter.format(None, PlayerId(1))
        assert out is None


class TestPursuitObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_pursuit_started_does_not_depend_on_recipient(self):
        """PursuitStarted は recipient に依存しない（出力は常に同一）。"""
        ctx = _make_context()
        formatter = PursuitObservationFormatter(ctx)
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=_build_pursuit_snapshot(),
            last_known=_build_pursuit_last_known(),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
        assert out1.observation_category == out2.observation_category

    def test_pursuit_failed_does_not_depend_on_recipient(self):
        """PursuitFailed は recipient に依存しない。"""
        ctx = _make_context()
        formatter = PursuitObservationFormatter(ctx)
        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.TARGET_MISSING,
            target_snapshot=None,
            last_known=_build_pursuit_last_known(),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
        assert out1.schedules_turn == out2.schedules_turn
        assert out1.breaks_movement == out2.breaks_movement
