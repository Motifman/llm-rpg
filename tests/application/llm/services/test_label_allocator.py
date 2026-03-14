"""LabelAllocator と SectionBuildResult のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    PlayerToolRuntimeTargetDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._label_allocator import (
    DEFAULT_LABEL_PREFIXES,
    LabelAllocator,
    SectionBuildResult,
)


class TestSectionBuildResult:
    """SectionBuildResult のテスト。"""

    def test_empty_returns_empty_result(self):
        result = SectionBuildResult.empty()
        assert result.lines == []
        assert result.targets == {}

    def test_construct_with_valid_lines_and_targets(self):
        target = PlayerToolRuntimeTargetDto(
            label="P1",
            kind="player",
            display_name="Bob",
            player_id=2,
            world_object_id=100,
        )
        result = SectionBuildResult(
            lines=["- P1: Bob"],
            targets={"P1": target},
        )
        assert result.lines == ["- P1: Bob"]
        assert result.targets == {"P1": target}
        assert result.targets["P1"].player_id == 2

    def test_raises_when_lines_is_not_list(self):
        with pytest.raises(TypeError) as exc_info:
            SectionBuildResult(lines="not a list", targets={})
        assert "lines must be list" in str(exc_info.value)

    def test_raises_when_targets_is_not_dict(self):
        with pytest.raises(TypeError) as exc_info:
            SectionBuildResult(lines=[], targets=["not", "dict"])
        assert "targets must be dict" in str(exc_info.value)

    def test_raises_when_targets_key_is_not_str(self):
        target = PlayerToolRuntimeTargetDto(
            label="P1",
            kind="player",
            display_name="Bob",
            player_id=2,
            world_object_id=100,
        )
        with pytest.raises(TypeError) as exc_info:
            SectionBuildResult(lines=[], targets={123: target})
        assert "targets keys must be str" in str(exc_info.value)

    def test_raises_when_targets_value_is_not_tool_runtime_target_dto(self):
        with pytest.raises(TypeError) as exc_info:
            SectionBuildResult(lines=[], targets={"P1": "not a dto"})
        assert "targets values must be ToolRuntimeTargetDto" in str(exc_info.value)


class TestLabelAllocator:
    """LabelAllocator のテスト。"""

    def test_next_returns_incrementing_labels_for_prefix(self):
        allocator = LabelAllocator()
        assert allocator.next("P") == "P1"
        assert allocator.next("P") == "P2"
        assert allocator.next("P") == "P3"
        assert allocator.next("S") == "S1"
        assert allocator.next("S") == "S2"

    def test_next_uses_default_prefixes_when_no_initial_counters(self):
        allocator = LabelAllocator()
        for p in DEFAULT_LABEL_PREFIXES:
            assert allocator.next(p) == f"{p}1"

    def test_next_with_initial_counters_starts_from_next_value(self):
        allocator = LabelAllocator(initial_counters={"P": 3, "S": 0})
        assert allocator.next("P") == "P4"
        assert allocator.next("P") == "P5"
        assert allocator.next("S") == "S1"

    def test_get_counter_returns_current_count(self):
        allocator = LabelAllocator()
        assert allocator.get_counter("P") == 0
        allocator.next("P")
        assert allocator.get_counter("P") == 1
        allocator.next("P")
        assert allocator.get_counter("P") == 2

    def test_get_counter_for_unknown_prefix_returns_zero(self):
        allocator = LabelAllocator()
        assert allocator.get_counter("XX") == 0

    def test_counters_snapshot_returns_copy(self):
        allocator = LabelAllocator()
        allocator.next("P")
        snapshot = allocator.counters_snapshot()
        assert snapshot["P"] == 1
        snapshot["P"] = 999
        assert allocator.get_counter("P") == 1

    def test_next_with_custom_prefix_not_in_default(self):
        allocator = LabelAllocator()
        assert allocator.next("LA") == "LA1"
        assert allocator.next("LA") == "LA2"

    def test_raises_when_prefix_is_empty(self):
        allocator = LabelAllocator()
        with pytest.raises(ValueError) as exc_info:
            allocator.next("")
        assert "prefix must not be empty" in str(exc_info.value)

    def test_raises_when_prefix_is_not_str(self):
        allocator = LabelAllocator()
        with pytest.raises(TypeError) as exc_info:
            allocator.next(123)  # type: ignore[arg-type]
        assert "prefix must be str" in str(exc_info.value)

    def test_raises_when_initial_counters_is_not_dict(self):
        with pytest.raises(TypeError) as exc_info:
            LabelAllocator(initial_counters=[("P", 0)])  # type: ignore[arg-type]
        assert "initial_counters must be dict or None" in str(exc_info.value)

    def test_raises_when_initial_counters_key_is_not_str(self):
        with pytest.raises(TypeError) as exc_info:
            LabelAllocator(initial_counters={123: 0})  # type: ignore[dict-item]
        assert "initial_counters keys must be str" in str(exc_info.value)

    def test_raises_when_initial_counters_value_is_negative(self):
        with pytest.raises(TypeError) as exc_info:
            LabelAllocator(initial_counters={"P": -1})
        assert "initial_counters values must be non-negative int" in str(exc_info.value)
