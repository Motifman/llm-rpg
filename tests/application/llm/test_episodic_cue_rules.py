"""決定論的 episodic cue ルール（runtime / tool / structured）の検証。"""

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    MAX_EPISODIC_CUES,
    build_episodic_cues_for_tool_turn,
)


class TestEpisodicCueDeterminism:
    """同一入力から同一 cue 列が得られること"""

    def test_same_inputs_yield_identical_tuple(self) -> None:
        """すべての入力を固定すると cue の tuple が完全一致する。"""
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
        args = {"emotion_hint": "caution", "world_object_id": 99}
        obs = {"spot_id_value": 12, "world_object_id_value": 42, "actor": "Alice"}
        res_ok = LlmCommandResultDto(success=True, message="ok")

        a = build_episodic_cues_for_tool_turn(
            tool_name="spot_graph_interact",
            canonical_arguments=args,
            runtime_context=rt,
            command_result=res_ok,
            observation_structured=obs,
        )
        b = build_episodic_cues_for_tool_turn(
            tool_name="spot_graph_interact",
            canonical_arguments=args,
            runtime_context=rt,
            command_result=res_ok,
            observation_structured=obs,
        )
        assert a == b
        assert all(isinstance(c, EpisodicCue) for c in a)


class TestRuntimeLocationCues:
    """runtime の場所 ID が cue になること"""

    def test_spot_area_sub_loc_from_runtime(self) -> None:
        """current_spot_id / current_area_ids / current_sub_location_id がそれぞれ対応軸になる。"""
        rt = ToolRuntimeContextDto(
            targets={},
            current_spot_id=100,
            current_sub_location_id=7,
            current_area_ids=(11, 11, 5),
        )
        cues = build_episodic_cues_for_tool_turn(
            tool_name="no_op",
            canonical_arguments={},
            runtime_context=rt,
            command_result=LlmCommandResultDto(success=True, message=""),
            observation_structured=None,
        )
        canon = {c.to_canonical() for c in cues}
        assert "place_spot:100" in canon
        assert "sub_loc:7" in canon
        assert "tile_area:5" in canon
        assert "tile_area:11" in canon
        assert sum(1 for c in cues if c.axis == "tile_area") == 2


class TestOutcomeCue:
    """tool success/failure が outcome cue になること (#526 後続 Fix D)。

    成功は意味のない一致 (= ほぼ全 episode が成功するため index として無価値)
    なので cue 化しない。失敗は希少で意味があるので残す。
    """

    def test_success_は_outcome_cue_を_付与しない(self) -> None:
        """成功時は ``outcome:success`` を出さない (#526 後続 Fix D)。

        Why: 実 run の trace 解析で「ほぼ全 episode が outcome:success を持ち、
        毎ターン全 successful episode が hit して recall が肥大する」ことが
        判明した。outcome cue は「失敗で何が起きたか」のときだけ意味があり、
        成功は cue として価値がない (index の選択性が極端に低い)。
        """
        cues = build_episodic_cues_for_tool_turn(
            tool_name="x",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="done"),
        )
        assert not any(c.axis == "outcome" for c in cues), (
            "成功 outcome cue が混入している: " + repr(cues)
        )

    def test_failure_outcome_with_error_code(self) -> None:
        """失敗時は failure と error_code を結合した単一 value とする。"""
        cues = build_episodic_cues_for_tool_turn(
            tool_name="x",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(
                success=False,
                message="no",
                error_code="TRAP_TRIGGERED",
            ),
        )
        oc = [c for c in cues if c.axis == "outcome"]
        assert len(oc) == 1
        assert oc[0].value == "failure_trap_triggered"

    def test_failure_without_error_code_では_outcome_failure_を_付与(self) -> None:
        """error_code 無しの失敗でも ``outcome:failure`` 単独 cue は残す。

        失敗は希少で「何かおかしかった」シグナルとして意味がある。
        """
        cues = build_episodic_cues_for_tool_turn(
            tool_name="x",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=False, message="?"),
        )
        oc = [c for c in cues if c.axis == "outcome"]
        assert len(oc) == 1
        assert oc[0].value == "failure"


class TestUnknownAndNoneIgnored:
    """unknown / None は安全に無視されること"""

    def test_none_runtime_and_observation_skipped(self) -> None:
        """runtime / structured が None でも構わず action は付く。

        #526 後続 Fix D: 成功時の outcome cue は無価値なので付けない。
        action cue は残す (tool 名の選択性は十分にある)。
        """
        cues = build_episodic_cues_for_tool_turn(
            tool_name="todo_append",
            canonical_arguments=None,
            runtime_context=None,
            command_result=LlmCommandResultDto(success=True, message=""),
            observation_structured=None,
        )
        canon = {c.to_canonical() for c in cues}
        assert "action:todo_append" in canon
        assert "outcome:success" not in canon  # Fix D: 成功は cue 化しない
        assert not any(c.axis == "place_spot" for c in cues)

    def test_structured_unknown_keys_ignored(self) -> None:
        """ホワイトリスト外の structured キーは cue に現れない。"""
        cues = build_episodic_cues_for_tool_turn(
            tool_name="y",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message=""),
            observation_structured={
                "type": "spot_object_state_changed",
                "free_form_story": "これは索引にしない",
                "nested": {"spot_id_value": 9},
            },
        )
        canon = {c.to_canonical() for c in cues}
        assert not any(k.startswith("object:") for k in canon or [])
        assert "place_spot:9" not in canon

    def test_movement_structured_keys_produce_place_spot_cues(self) -> None:
        """#526 後続 Fix B: 移動観測の ``from_spot_id_value`` / ``to_spot_id_value``
        が両方 ``place_spot`` cue に変換される。

        Why: 実 run の trace 解析で、移動観測は ``spot_id_value`` ではなく
        ``from_spot_id_value`` / ``to_spot_id_value`` のペアを emit していて、
        cue rule が読まないため episode に place_spot が貼られない問題が
        判明した。両方とも「ここに居た」「ここに来た」という意味で recall
        の手がかりに値するので両方 cue 化する (dedupe は呼出側で行われる)。
        """
        cues = build_episodic_cues_for_tool_turn(
            tool_name="spot_graph_travel_to",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message=""),
            observation_structured={
                "type": "entity_left_spot",
                "from_spot_id_value": 1,
                "to_spot_id_value": 2,
                "actor": "kaito",
            },
        )
        canon = {c.to_canonical() for c in cues}
        assert "place_spot:1" in canon, f"from_spot_id_value が cue 化されていない: {canon}"
        assert "place_spot:2" in canon, f"to_spot_id_value が cue 化されていない: {canon}"

    def test_invalid_emotion_hint_skipped(self) -> None:
        """ENUM にない emotion_hint は無視する。"""
        cues = build_episodic_cues_for_tool_turn(
            tool_name="z",
            canonical_arguments={"emotion_hint": "made_up_feeling"},
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message=""),
        )
        assert not any(c.axis == "emotion" for c in cues)


class TestDedupeAndCaps:
    """重複排除と上限"""

    def test_duplicate_place_spot_deduped(self) -> None:
        """runtime と structured で同じ spot が一度だけ残る。"""
        rt = ToolRuntimeContextDto(targets={}, current_spot_id=5)
        cues = build_episodic_cues_for_tool_turn(
            tool_name="a",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=LlmCommandResultDto(success=True, message=""),
            observation_structured={"spot_id_value": 5},
        )
        assert sum(1 for c in cues if c.to_canonical() == "place_spot:5") == 1

    def test_respects_max_cue_count(self) -> None:
        """cue 数が上限を超えない。"""
        areas = tuple(range(MAX_EPISODIC_CUES + 10))
        rt = ToolRuntimeContextDto(targets={}, current_area_ids=areas)
        cues = build_episodic_cues_for_tool_turn(
            tool_name="b",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=LlmCommandResultDto(success=True, message=""),
        )
        assert len(cues) <= MAX_EPISODIC_CUES

    def test_massive_tile_areas_do_not_drop_action_or_outcome(self) -> None:
        """
        current_area_ids が極端に多くても、先頭の action / outcome が
        MAX_EPISODIC_CUES 打ち切りで欠落しない（旧実装のレビューブロッカー回帰）。
        """
        areas = tuple(range(MAX_EPISODIC_CUES + 10))
        rt = ToolRuntimeContextDto(
            targets={},
            current_spot_id=1,
            current_sub_location_id=2,
            current_area_ids=areas,
        )
        cues = build_episodic_cues_for_tool_turn(
            tool_name="spot_graph_heavy_scan",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=LlmCommandResultDto(
                success=False,
                message="ng",
                error_code="AREA_OVERFLOW",
            ),
        )
        canon = {c.to_canonical() for c in cues}
        assert "action:spot_graph_heavy_scan" in canon
        assert "outcome:failure_area_overflow" in canon
