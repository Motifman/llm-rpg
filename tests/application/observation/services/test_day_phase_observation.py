"""DayPhaseChangedEvent の観測（recipient strategy + formatter）テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.day_phase_formatter import (
    DayPhaseObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.day_phase_recipient_strategy import (
    DayPhaseRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    DayPhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _build_graph(spots: dict[int, bool], placements: dict[int, int]) -> SpotGraphAggregate:
    """spots: {spot_id: is_outdoor}, placements: {entity_id: spot_id}"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for sid, outdoor in spots.items():
        graph.add_spot(
            SpotNode(
                spot_id=SpotId.create(sid),
                name=f"spot_{sid}",
                description="",
                category=SpotCategoryEnum.TOWN,
                parent_id=None,
                is_outdoor=outdoor,
            )
        )
    for eid, sid in placements.items():
        graph.place_entity(EntityId.create(eid), SpotId.create(sid))
    graph.clear_events()
    return graph


def _make_status_repo(player_ids: list[int]):
    statuses = []
    for pid in player_ids:
        s = MagicMock()
        s.player_id = PlayerId(pid)
        statuses.append(s)
    repo = MagicMock()
    repo.find_all.return_value = statuses
    return repo


def _make_event() -> DayPhaseChangedEvent:
    return DayPhaseChangedEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraph",
        from_phase_name="evening",
        to_phase_name="night",
        to_phase_display_text="夜",
        ambient_light=0.1,
        is_dark=True,
    )


class TestDayPhaseRecipientStrategy:
    """DayPhaseRecipientStrategy の配信先解決挙動。"""

    def test_outdoor_player_receives(self) -> None:
        """屋外スポットにいるプレイヤーは DayPhase 変化を観測する。"""
        graph = _build_graph({1: True}, {1: 1})
        repo = MagicMock()
        repo.find_graph.return_value = graph
        strategy = DayPhaseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=repo,
            player_status_repository=_make_status_repo([1]),
        )

        recipients = strategy.resolve(_make_event())
        assert {p.value for p in recipients} == {1}

    def test_indoor_player_excluded(self) -> None:
        """屋内スポットにいるプレイヤーは配信先から除外される。"""
        graph = _build_graph({1: False}, {1: 1})
        repo = MagicMock()
        repo.find_graph.return_value = graph
        strategy = DayPhaseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=repo,
            player_status_repository=_make_status_repo([1]),
        )

        assert strategy.resolve(_make_event()) == []

    def test_mixed_indoor_outdoor_filters_correctly(self) -> None:
        """屋内屋外が混在しても、屋外スポットにいるプレイヤーのみ抽出される。"""
        graph = _build_graph(
            spots={1: True, 2: False},
            placements={1: 1, 2: 2, 3: 1},
        )
        repo = MagicMock()
        repo.find_graph.return_value = graph
        strategy = DayPhaseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=repo,
            player_status_repository=_make_status_repo([1, 2, 3]),
        )

        recipients = strategy.resolve(_make_event())
        assert {p.value for p in recipients} == {1, 3}

    def test_supports_only_day_phase_event(self) -> None:
        """supports() は DayPhaseChangedEvent のみ True を返す。"""
        graph = _build_graph({1: True}, {})
        repo = MagicMock()
        repo.find_graph.return_value = graph
        strategy = DayPhaseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=repo,
            player_status_repository=_make_status_repo([]),
        )
        assert strategy.supports(_make_event()) is True

        class Other:
            pass

        assert strategy.supports(Other()) is False


class TestDayPhaseObservationFormatter:
    """DayPhaseObservationFormatter の出力フォーマット挙動。"""

    def test_formats_day_phase_change(self) -> None:
        """DayPhaseChangedEvent から environment カテゴリの ObservationOutput を生成する。"""
        ctx = ObservationFormatterContext(
            name_resolver=ObservationNameResolver(),
            item_repository=None,
        )
        formatter = DayPhaseObservationFormatter(ctx)

        out = formatter.format(_make_event(), PlayerId(1))
        assert out is not None
        assert "夜" in out.prose
        assert out.observation_category == "environment"
        assert out.schedules_turn is False
        assert out.breaks_movement is False
        assert out.structured["from_phase"] == "evening"
        assert out.structured["to_phase"] == "night"
        assert out.structured["is_dark"] is True

    def test_returns_none_for_other_events(self) -> None:
        """DayPhaseChangedEvent 以外のイベントには None を返す。"""
        ctx = ObservationFormatterContext(
            name_resolver=ObservationNameResolver(),
            item_repository=None,
        )
        formatter = DayPhaseObservationFormatter(ctx)
        assert formatter.format("not_an_event", PlayerId(1)) is None
