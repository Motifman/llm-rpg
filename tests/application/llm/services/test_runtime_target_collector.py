"""RuntimeTargetCollector のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._runtime_target_collector import (
    RuntimeTargetCollector,
)


def _make_player_target(label: str, player_id: int = 1) -> PlayerToolRuntimeTargetDto:
    return PlayerToolRuntimeTargetDto(
        label=label,
        kind="player",
        display_name="Test",
        player_id=player_id,
        world_object_id=100,
    )


def _make_destination_target(label: str) -> DestinationToolRuntimeTargetDto:
    return DestinationToolRuntimeTargetDto(
        label=label,
        kind="destination",
        display_name="Test Spot",
        spot_id=1,
        destination_type="spot",
    )


class TestRuntimeTargetCollector:
    """RuntimeTargetCollector のテスト。"""

    def test_add_stores_target_under_label(self):
        collector = RuntimeTargetCollector()
        target = _make_player_target("P1")

        collector.add("P1", target)

        assert collector.get("P1") is target
        assert collector.get_targets() == {"P1": target}

    def test_add_multiple_targets(self):
        collector = RuntimeTargetCollector()
        t1 = _make_player_target("P1", 1)
        t2 = _make_player_target("P2", 2)

        collector.add("P1", t1)
        collector.add("P2", t2)

        assert collector.get("P1") is t1
        assert collector.get("P2") is t2
        assert len(collector.get_targets()) == 2

    def test_add_all_merges_targets(self):
        collector = RuntimeTargetCollector()
        t1 = _make_player_target("P1")
        t2 = _make_destination_target("S1")

        collector.add_all({"P1": t1, "S1": t2})

        assert collector.get("P1") is t1
        assert collector.get("S1") is t2

    def test_add_all_overwrites_existing_label(self):
        collector = RuntimeTargetCollector()
        t1 = _make_player_target("P1", 1)
        t2 = _make_player_target("P1", 2)

        collector.add("P1", t1)
        collector.add_all({"P1": t2})

        assert collector.get("P1") is t2
        assert collector.get("P1").player_id == 2

    def test_get_returns_none_when_label_missing(self):
        collector = RuntimeTargetCollector()
        assert collector.get("X99") is None

    def test_get_targets_returns_copy(self):
        collector = RuntimeTargetCollector()
        target = _make_player_target("P1")
        collector.add("P1", target)

        d = collector.get_targets()
        assert d == {"P1": target}
        d.clear()
        assert collector.get("P1") is target

    def test_raises_when_add_receives_none_target(self):
        collector = RuntimeTargetCollector()
        with pytest.raises(TypeError) as exc_info:
            collector.add("P1", None)  # type: ignore[arg-type]
        assert "target must be ToolRuntimeTargetDto" in str(exc_info.value)

    def test_raises_when_add_receives_non_dto(self):
        collector = RuntimeTargetCollector()
        with pytest.raises(TypeError) as exc_info:
            collector.add("P1", "not a dto")  # type: ignore[arg-type]
        assert "target must be ToolRuntimeTargetDto" in str(exc_info.value)

    def test_raises_when_add_duplicate_label(self):
        collector = RuntimeTargetCollector()
        t1 = _make_player_target("P1", 1)
        t2 = _make_player_target("P1", 2)
        collector.add("P1", t1)
        with pytest.raises(ValueError) as exc_info:
            collector.add("P1", t2)
        assert "Duplicate label" in str(exc_info.value)

    def test_raises_when_add_all_receives_none(self):
        collector = RuntimeTargetCollector()
        with pytest.raises(TypeError) as exc_info:
            collector.add_all(None)  # type: ignore[arg-type]
        assert "targets must be dict" in str(exc_info.value)

    def test_raises_when_add_all_value_is_not_dto(self):
        collector = RuntimeTargetCollector()
        with pytest.raises(TypeError) as exc_info:
            collector.add_all({"P1": "invalid"})
        assert "targets values must be ToolRuntimeTargetDto" in str(exc_info.value)
