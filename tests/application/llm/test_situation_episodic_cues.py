"""現在局面（runtime + 直近観測 structured + 任意で直近行動）からの situation cue 生成の検証。"""

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    InventoryToolRuntimeTargetDto,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
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

    def test_matches_tool_turn_when_tool_prefix(self) -> None:
        """
        tool / outcome / canonical を付けない tool_turn と situation は cue 列が一致する。
        topic は semantic recall 用の query 側 cue なので、通常の situation には載せない。
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
        assert all(c.axis != "topic" for c in situation)
        assert all(c.axis != "topic" for c in tool_turn_equivalent)

    def test_topic_cues_generated_from_runtime_target_display_names(self) -> None:
        """semantic 検索入力として明示したときだけ、対象名と所持品名から topic cue が生成される。"""
        rt = ToolRuntimeContextDto(
            targets={
                "O1": WorldObjectToolRuntimeTargetDto(
                    label="O1",
                    kind="world_object",
                    display_name="古い焚き火跡",
                    world_object_id=31,
                ),
                "I1": InventoryToolRuntimeTargetDto(
                    label="I1",
                    kind="inventory_item",
                    display_name="火打ち石",
                    item_instance_id=4,
                ),
            },
            current_spot_id=5,
        )
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            include_topic_cues=True,
        )
        canon = {c.to_canonical() for c in cues}
        assert "topic:古い焚き火跡" in canon
        assert "topic:火打ち石" in canon

    def test_topic_cues_are_disabled_by_default_for_saved_paths(self) -> None:
        """既定では runtime target や semantic_topic_words から topic を作らず、保存経路に混ざらない。"""
        rt = ToolRuntimeContextDto(
            targets={
                "O1": WorldObjectToolRuntimeTargetDto(
                    label="O1",
                    kind="world_object",
                    display_name="山頂の狼煙台",
                    world_object_id=77,
                )
            },
            current_spot_id=9,
        )
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            semantic_topic_words=("火", "食料"),
        )
        assert all(c.axis != "topic" for c in cues)

    def test_topic_only_words_do_not_disable_temporal_fallback_by_default(self) -> None:
        """episodic 側の topic-only 入力は既定で空 cue のままになり、temporal fallback を阻害しない。"""
        cues = build_situation_episodic_cues(
            runtime_context=None,
            semantic_topic_words=("火", "食料"),
        )
        assert cues == ()

    def test_topic_cues_are_not_saved_on_tool_turn_episode_cues(self) -> None:
        """episode 保存側の tool turn cue には topic を保存せず、episodic 索引を動かさない。"""
        rt = ToolRuntimeContextDto(
            targets={
                "O1": WorldObjectToolRuntimeTargetDto(
                    label="O1",
                    kind="world_object",
                    display_name="山頂の狼煙台",
                    world_object_id=77,
                )
            },
            current_spot_id=9,
        )
        cues = build_episodic_cues_for_tool_turn(
            tool_name="interact",
            canonical_arguments=None,
            runtime_context=rt,
            command_result=None,
        )
        assert all(c.axis != "topic" for c in cues)

    def test_topic_cues_are_outside_episodic_budget(self) -> None:
        """既存 cue が上限に達する豊かな状況でも、topic cue は上限外で落ちない。"""
        targets = {
            f"O{i:02d}": WorldObjectToolRuntimeTargetDto(
                label=f"O{i:02d}",
                kind="world_object",
                display_name=f"目印{i:02d}",
                world_object_id=i,
            )
            for i in range(MAX_EPISODIC_CUES + 5)
        }
        rt = ToolRuntimeContextDto(targets=targets, current_spot_id=1)
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            include_topic_cues=True,
        )
        non_topic = [c for c in cues if c.axis != "topic"]
        canon = {c.to_canonical() for c in cues}
        assert len(non_topic) == MAX_EPISODIC_CUES
        assert len(cues) > MAX_EPISODIC_CUES
        assert "topic:目印00" in canon

    def test_without_latest_action_or_outcome_axes(self) -> None:
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


class TestSituationCueFreeTextProse:
    """Issue #283 後続: observation_prose + noun_matcher で自由文 cue 抽出。"""

    def test_matcher_prose_included_proper_noun_cue(self) -> None:
        """``WorldNounMatcher`` を渡せば prose 中の固有名詞が cue 化される。
        ``OBSERVATION_FREETEXT`` source で来るので structured cue と区別可能。"""
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
        from ai_rpg_world.application.llm.services.world_noun_matcher import (
            WorldNounMatcherBuilder,
        )

        matcher = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured=None,
            observation_prose="リン、書架A で待ってるよ",
            noun_matcher=matcher,
        )
        assert any(
            c.to_canonical() == "place_spot:3"
            and c.source == EpisodicCueSource.OBSERVATION_FREETEXT
            for c in cues
        )

    def test_matcher_unspecified_after_compatible(self) -> None:
        """noun_matcher を渡さなければ prose は走査されない (旧挙動)。"""
        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured=None,
            observation_prose="リン、書架A で待ってるよ",
            # noun_matcher 未指定
        )
        # place_spot:3 は立たない
        assert all(c.to_canonical() != "place_spot:3" for c in cues)

    def test_prose_unspecified(self) -> None:
        """``observation_prose=None`` なら matcher があってもスキップする。"""
        from ai_rpg_world.application.llm.services.world_noun_matcher import (
            WorldNounMatcherBuilder,
        )

        matcher = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured=None,
            observation_prose=None,
            noun_matcher=matcher,
        )
        assert all(c.to_canonical() != "place_spot:3" for c in cues)

    def test_matcher_cue_raises_exception(self) -> None:
        """matcher 実装が壊れて例外を投げても build は空 cue で続行する
        (prompt build を止めない)。"""

        class _BrokenMatcher:
            def find_in_text(self, text: str):  # noqa: ARG002
                raise RuntimeError("intentionally broken")

        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured=None,
            observation_prose="any",
            noun_matcher=_BrokenMatcher(),
        )
        # 失敗しても tuple が返り、prose 由来 cue は単に欠落するだけ
        assert isinstance(cues, tuple)

    def test_cue_duplicate(self) -> None:
        """structured.spot_id_value=3 と prose 中の「書架A」が両方 place_spot:3
        を指せば、_validate_and_dedupe で 1 件に正規化される。"""
        from ai_rpg_world.application.llm.services.world_noun_matcher import (
            WorldNounMatcherBuilder,
        )

        matcher = WorldNounMatcherBuilder().add_spot("書架A", spot_id=3).build()
        cues = build_situation_episodic_cues(
            runtime_context=ToolRuntimeContextDto.empty(),
            observation_structured={"spot_id_value": 3},
            observation_prose="書架A で待ってる",
            noun_matcher=matcher,
        )
        # place_spot:3 が 1 件だけ
        assert sum(1 for c in cues if c.to_canonical() == "place_spot:3") == 1
