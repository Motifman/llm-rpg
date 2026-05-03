"""ActionEpisodeDraftBuilder が tool 結果から決定論的に SubjectiveEpisode を組むことの検証。"""

import importlib.util
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.action_episode_draft_builder import (
    ActionEpisodeDraftBuilder,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _npc_target(player_id: int, label: str = "npc_a") -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label=label,
        kind="monster",
        display_name="Goblin",
        player_id=player_id,
    )


class TestActionEpisodeDraftBuilderHappyPath:
    """代表的成功・失敗・予測誤差なしおよび観測付きドラフト"""

    def test_success_tool_result_builds_episode(self) -> None:
        """成功結果から outcome が成功になり、ソース event id が載るドラフトになる。"""
        builder = ActionEpisodeDraftBuilder()
        rt = ToolRuntimeContextDto(targets={"g": _npc_target(99)}, current_spot_id=7)
        res = builder.build(
            player_id=1,
            occurred_at=_utc(2026, 5, 3, 14, 0),
            tool_name="spot_graph_interact",
            canonical_arguments={
                "intention": "箱の中身を確かめる",
                "emotion_hint": "caution",
            },
            runtime_context=rt,
            command_result=LlmCommandResultDto(success=True, message="開封に成功した。"),
            action_summary="宝箱を調べた",
            result_summary="開封に成功した。",
            episodic_cues=(),
        )
        assert res.episode_id
        assert "成功" in res.outcome
        assert res.prediction_error is None
        assert res.interpreted is None
        assert res.intended_next is None
        assert res.cues == ()
        assert "entity:monster:99" in res.who

    def test_failure_tool_result_builds_episode(self) -> None:
        """失敗時は outcome に failure を含め error_code が反映される。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=2,
            occurred_at=_utc(2026, 5, 3, 15, 0),
            tool_name="spot_graph_interact",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(
                success=False,
                message="罠が発動した。",
                error_code="TRAP_TRIGGERED",
            ),
            action_summary="",
            result_summary="罠が発動した。",
            episodic_cues=(),
        )
        assert "失敗" in ep.outcome
        assert "TRAP_TRIGGERED" in ep.outcome
        assert ep.felt is None

    def test_expected_result_optional_episode_ok(self) -> None:
        """expected_result が無いとき prediction_error は None のままでも成立する。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=3,
            occurred_at=_utc(2026, 5, 3, 16, 0),
            tool_name="wait_turn",
            canonical_arguments={"emotion_hint": "neutral"},
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="待機した"),
            action_summary="待機",
            result_summary="待機した",
            episodic_cues=(),
        )
        assert ep.expected is None
        assert ep.prediction_error is None

    def test_prediction_error_when_expected_differs_from_summary(self) -> None:
        """expected と結果要約が食い違うと単純な予測誤差文が載る。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=4,
            occurred_at=_utc(2026, 5, 3, 17, 0),
            tool_name="open",
            canonical_arguments={"expected_result": "中身が見える"},
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=False, message="鍵がかかっている"),
            action_summary="開ける",
            result_summary="鍵がかかっている",
            episodic_cues=(),
        )
        assert ep.expected == "中身が見える"
        assert ep.prediction_error is not None
        assert "予想:" in ep.prediction_error

    def test_prediction_error_none_when_expected_matches_summary(self) -> None:
        """予想文字列が結果要約と同一なら予測誤差フィールドは空にする。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=412,
            occurred_at=_utc(2026, 5, 3, 17, 30),
            tool_name="probe",
            canonical_arguments={"expected_result": "完全一致ライン"},
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="完全一致ライン"),
            action_summary="-",
            result_summary="完全一致ライン",
            episodic_cues=(),
        )
        assert ep.prediction_error is None


class TestObservedSanityAndGameTime:
    """observed の情報源ゲートとゲーム内時刻ラベルの決定論的反映"""

    def test_observed_stays_within_passed_summaries_when_no_observation(self) -> None:
        """観測なしでは observed は result_summary / message の合成規則に従う（捏造しない）。"""
        builder = ActionEpisodeDraftBuilder()
        rs_only = builder.build(
            player_id=5,
            occurred_at=_utc(2026, 5, 3, 18, 0),
            tool_name="no_op_stub",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="alpha-only-core"),
            action_summary="x",
            result_summary="alpha-only-core",
            episodic_cues=(),
        )
        assert rs_only.observed == "alpha-only-core"

        msg_diff = builder.build(
            player_id=5,
            occurred_at=_utc(2026, 5, 3, 18, 1),
            tool_name="no_op_stub",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="full detail line"),
            action_summary="x",
            result_summary="short sum",
            episodic_cues=(),
        )
        assert msg_diff.observed == "short sum\nfull detail line"

    def test_observed_falls_back_to_message_when_summary_empty(self) -> None:
        """result_summary が空でも command_result.message があれば observed にフォールバックする。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=501,
            occurred_at=_utc(2026, 5, 3, 18, 2),
            tool_name="minimal_ok",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=False, message=" fall back msg "),
            action_summary="-",
            result_summary="",
            episodic_cues=(),
        )
        assert ep.observed == "fall back msg"
        assert "fall back msg" in ep.outcome or "fall back msg" in ep.recall_text

    def test_observation_prose_only_appends_given_output(self) -> None:
        """観測 prose は ObservationEntry が渡されたときのみ付与される（捏造しない）。"""
        builder = ActionEpisodeDraftBuilder()
        prose = "周囲に焦げた臭いが漂った。"
        out = ObservationOutput(prose=prose, structured={})
        obs = ObservationEntry(occurred_at=_utc(2026, 5, 3, 19, 0), output=out)
        ep = builder.build(
            player_id=6,
            occurred_at=_utc(2026, 5, 3, 19, 30),
            tool_name="explore_area",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="探索続行"),
            action_summary="周囲を確認",
            result_summary="探索続行",
            recent_observation=obs,
            episodic_cues=(),
        )
        assert ep.observed.endswith(prose)

    def test_game_time_label_from_recent_observation(self) -> None:
        """ゲーム内時刻ラベルは観測エントリからのみ取り、捏造しない。"""
        builder = ActionEpisodeDraftBuilder()
        out = ObservationOutput(prose="x", structured={})
        obs = ObservationEntry(
            occurred_at=_utc(2026, 5, 3, 20, 0),
            output=out,
            game_time_label="Day 7 · dusk",
        )
        ep_no = builder.build(
            player_id=7,
            occurred_at=_utc(2026, 5, 3, 20, 15),
            tool_name="t",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="done"),
            action_summary="a",
            result_summary="done",
            episodic_cues=(),
        )
        assert ep_no.game_time_label is None

        ep_yes = builder.build(
            player_id=7,
            occurred_at=None,
            tool_name="t",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="done"),
            action_summary="a",
            result_summary="done",
            recent_observation=obs,
            episodic_cues=(),
        )
        assert ep_yes.game_time_label == "Day 7 · dusk"
        assert ep_yes.occurred_at == obs.occurred_at


class TestFiveWOneHFieldProvenance:
    """5W1H（＋構造化された where/how）フィールドごとの入力源が説明できること"""

    def test_field_sources_map_to_explicit_inputs(self) -> None:
        """
        Who: ToolRuntimeTargetDto と観測 structured.actor 由来の canonical。
        Where: ToolRuntimeContextDto が EpisodeLocation へ直行。
        When: occurred_at。
        What: action_summary と tool_name と結果要約。
        Why: canonical_arguments["intention"]。
        How: EpisodeAction(tool_name と canonical_arguments JSON)。
        Observed/outcome/recall_text: メッセージ・要約・許可された観測 prose のみ。
        """
        structured = {"actor": 502}
        out = ObservationOutput(prose="", structured=structured)
        obs = ObservationEntry(occurred_at=_utc(2026, 5, 3, 21, 0), output=out)

        rt = ToolRuntimeContextDto(
            targets={
                "enemy": ToolRuntimeTargetDto(label="e", kind="Monster", display_name="M", player_id=100)
            },
            current_spot_id=12,
            current_sub_location_id=3,
            current_area_ids=(9, 10),
            current_x=1,
            current_y=2,
            current_z=0,
        )
        canon = {
            "intention": "倒す",
            "expected_result": "ダメージを与える",
            "emotion_hint": "determination",
        }

        ep = ActionEpisodeDraftBuilder().build(
            player_id=8,
            occurred_at=_utc(2026, 5, 3, 21, 5),
            tool_name="attack_target",
            canonical_arguments=canon,
            runtime_context=rt,
            command_result=LlmCommandResultDto(success=True, message="命中"),
            action_summary="攻撃した",
            result_summary="命中",
            recent_observation=obs,
            episodic_cues=(),
        )

        assert ep.who == ("entity:monster:100", "entity:actor:502")
        assert ep.location.spot_id == 12
        assert ep.location.sub_location_id == 3
        assert ep.location.tile_area_ids == (9, 10)
        assert ep.location.x == 1 and ep.location.y == 2 and ep.location.z == 0
        assert ep.occurred_at == _utc(2026, 5, 3, 21, 5)
        assert "攻撃した" in ep.what and "attack_target" in ep.what and "命中" in ep.what
        assert ep.why == "倒す"
        assert ep.action is not None and ep.action.tool_name == "attack_target"
        assert ep.action.canonical_arguments_text is not None
        assert '"emotion_hint"' in ep.action.canonical_arguments_text
        assert ep.felt == "determination"


class TestEpisodicCueIntegrationOptional:
    """cue が未マージのとき既定は空になり、明示注入または将来の統合パスがあること"""

    def test_injected_empty_cues_on_main_without_cue_rules_module(self) -> None:
        """episodic_cues=() で cue rules 依存なしにドラフトできる（並列開発向け）。"""
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=9,
            occurred_at=_utc(2026, 5, 3, 22, 0),
            tool_name="sample_tool",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto.empty(),
            command_result=LlmCommandResultDto(success=True, message="ok"),
            action_summary="a",
            result_summary="ok",
            episodic_cues=(),
        )
        assert ep.cues == ()

    def test_default_cues_empty_when_cue_rules_not_in_repo(self) -> None:
        """episodic_cues を省略した場合、`episodic_cue_rules` が無ければ cues は自動的に空。"""
        cue_spec = importlib.util.find_spec("ai_rpg_world.application.llm.services.episodic_cue_rules")
        if cue_spec is not None:
            pytest.skip("episodic_cue_rules が同梱のときは、この main 単体検証対象外")
        builder = ActionEpisodeDraftBuilder()
        ep = builder.build(
            player_id=991,
            occurred_at=_utc(2026, 5, 3, 22, 11),
            tool_name="ambient_scan",
            canonical_arguments=None,
            runtime_context=ToolRuntimeContextDto(targets={}, current_spot_id=404),
            command_result=LlmCommandResultDto(success=True, message="ok"),
            action_summary="-",
            result_summary="ok",
        )
        assert ep.cues == ()
