"""現在局面（runtime + 直近観測 structured + 任意で直近行動）からの situation cue 生成の検証。"""

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import EpisodicCue
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    MAX_EPISODIC_CUES,
    build_episodic_cues_for_tool_turn,
    build_situation_episodic_cues,
)


class TestSituationCueDeterminism:
    """同一入力から同一 cue 列が得られること"""

    def test_same_inputs_yield_identical_tuple(self) -> None:
        """runtime と structured を固定すると cue の tuple が完全一致する。"""
        rt = ToolRuntimeContextDto(
            targets={
                "t1": WorldObjectToolRuntimeTargetDto(
                    label="t1",
                    kind="world_object",
                    display_name="箱",
                    world_object_id=42,
                )
            },
            current_spot_id=12,
            current_sub_location_id=9,
            current_area_ids=(3, 4),
        )
        obs = {"spot_id_value": 12, "world_object_id_value": 42, "actor": "Alice"}

        a = build_situation_episodic_cues(runtime_context=rt, observation_structured=obs)
        b = build_situation_episodic_cues(runtime_context=rt, observation_structured=obs)
        assert a == b
        assert all(isinstance(c, EpisodicCue) for c in a)


class TestSituationCueVocabulary:
    """保存側ルールと軸・語彙が揃うこと"""

    def test_matches_tool_turn_when_no_tool_prefix(self) -> None:
        """
        tool / outcome / canonical を付けない tool_turn と situation を同一入力にすると cue 列が一致する。
        これにより局面 cue と `build_episodic_cues_for_tool_turn` の runtime+structured 部分が共有される。
        """
        rt = ToolRuntimeContextDto(
            targets={
                "t1": WorldObjectToolRuntimeTargetDto(
                    label="t1",
                    kind="player",
                    display_name="相棒",
                    player_id=7,
                )
            },
            current_spot_id=5,
            current_sub_location_id=2,
            current_area_ids=(10, 20),
        )
        obs = {"spot_id_value": 5, "world_object_id_value": 99, "actor": 3}

        situation = build_situation_episodic_cues(runtime_context=rt, observation_structured=obs)
        tool_turn_equivalent = build_episodic_cues_for_tool_turn(
            tool_name="",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=None,
            observation_structured=obs,
        )
        assert situation == tool_turn_equivalent

    def test_without_latest_action_no_action_or_outcome_axes(self) -> None:
        """latest_action を渡さないときは action / outcome 軸を付与しない。"""
        rt = ToolRuntimeContextDto(targets={}, current_spot_id=1)
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            observation_structured={"spot_id_value": 1},
        )
        axes = {c.axis for c in cues}
        assert "action" not in axes
        assert "outcome" not in axes

    def test_latest_action_aligns_with_tool_turn_prefix(self) -> None:
        """§0.2: 直近行動を渡すと tool ターン先頭の action/outcome と同一正規化になる。"""
        rt = ToolRuntimeContextDto(targets={}, current_spot_id=1)
        obs = {"spot_id_value": 1}
        occurred = datetime(2026, 5, 3, 1, 2, 3, tzinfo=timezone.utc)
        entry = ActionResultEntry(
            occurred_at=occurred,
            action_summary="x",
            result_summary="y",
            success=False,
            error_code="NO_TOOL_CALL",
            tool_name="world_move_to",
        )
        situation = build_situation_episodic_cues(
            runtime_context=rt,
            observation_structured=obs,
            latest_action=entry,
        )
        tool_with_outcome = build_episodic_cues_for_tool_turn(
            tool_name="world_move_to",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=LlmCommandResultDto(
                success=False,
                message="m",
                error_code="NO_TOOL_CALL",
            ),
            observation_structured=obs,
        )
        assert situation == tool_with_outcome

    def test_runtime_place_and_observation_structured_fields(self) -> None:
        """spot / sub_loc / tile_area / entity / object が tool_turn と同じ canonical になる。"""
        rt = ToolRuntimeContextDto(
            targets={},
            current_spot_id=100,
            current_sub_location_id=7,
            current_area_ids=(11, 5),
        )
        cues = build_situation_episodic_cues(runtime_context=rt, observation_structured=None)
        canon = {c.to_canonical() for c in cues}
        assert "place_spot:100" in canon
        assert "sub_loc:7" in canon
        assert "tile_area:5" in canon
        assert "tile_area:11" in canon


class TestSituationCueDedupeAndCaps:
    """重複排除と上限"""

    def test_duplicate_place_spot_deduped(self) -> None:
        """runtime と structured で同じ spot が一度だけ残る。"""
        rt = ToolRuntimeContextDto(targets={}, current_spot_id=5)
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            observation_structured={"spot_id_value": 5},
        )
        assert sum(1 for c in cues if c.to_canonical() == "place_spot:5") == 1

    def test_respects_max_cue_count(self) -> None:
        """cue 数が上限を超えない。"""
        areas = tuple(range(MAX_EPISODIC_CUES + 10))
        rt = ToolRuntimeContextDto(targets={}, current_area_ids=areas)
        cues = build_situation_episodic_cues(runtime_context=rt, observation_structured=None)
        assert len(cues) <= MAX_EPISODIC_CUES


class TestSituationCueObservationUnknownKeys:
    """structured のホワイトリスト外は無視"""

    def test_structured_unknown_keys_ignored(self) -> None:
        """ホワイトリスト外の structured キーは cue に現れない。"""
        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured={
                "type": "spot_object_state_changed",
                "free_form_story": "これは索引にしない",
                "nested": {"spot_id_value": 9},
            },
        )
        canon = {c.to_canonical() for c in cues}
        assert "place_spot:9" not in canon
