"""ChunkEpisodeDraftBuilder が ChunkEncodingInput からルールのみで草案を埋めることの検証。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
    format_unified_timeline_as_recent_events_bullets,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput, ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestChunkEpisodeDraftBuilder:
    """チャンク入力から SubjectiveEpisode のルールフィールドが決定論的に埋まる。"""

    def test_rejects_chunk_without_actions(self) -> None:
        """ActionResultEntry が 0 件のときは ValueError（起動ゲートと整合）。"""
        inp = build_chunk_encoding_input(PlayerId(1), (), ())
        assert chunk_encoding_episode_generation_allowed(inp) is False
        with pytest.raises(ValueError, match="ActionResultEntry"):
            ChunkEpisodeDraftBuilder().build(inp)

    def test_observed_matches_unified_timeline_bullets(self) -> None:
        """observed は merge 済みタイムラインの箇条書きと一致（プロンプト一次情報に揃える）。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="雷が鳴った。",
                structured={},
                observation_category="environment",
            ),
            game_time_label="昼",
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="避難を試みた",
            result_summary="成功した。",
            tool_name="move",
        )
        inp = build_chunk_encoding_input(PlayerId(2), (obs,), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.observed == format_unified_timeline_as_recent_events_bullets(inp.unified_timeline)
        assert "[昼]" in ep.observed
        assert "move" in ep.what

    def test_interpreted_and_recall_none_for_llm_followup(self) -> None:
        """interpreted / recall_text は未生成（後続 E が埋める）。"""
        act = ActionResultEntry(
            occurred_at=datetime(2026, 5, 4, 11, 0, 0, tzinfo=timezone.utc),
            action_summary="x",
            result_summary="y",
            tool_name="inspect",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.interpreted is None
        assert ep.recall_text is None

    def test_occurred_at_is_latest_action_time(self) -> None:
        """occurred_at はチャンク内行動の最大 occurred_at（境界の「いつ」）。"""
        early = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        late = early + timedelta(seconds=30)
        a1 = ActionResultEntry(
            occurred_at=early,
            action_summary="a",
            result_summary="r1",
            tool_name="t1",
        )
        a2 = ActionResultEntry(
            occurred_at=late,
            action_summary="b",
            result_summary="r2",
            tool_name="t2",
            success=False,
            error_code="E1",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (a1, a2))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.occurred_at == late
        assert "失敗" in ep.outcome

    def test_who_and_location_from_observation_structured(self) -> None:
        """観測 structured から who 相当・spot（where）をルールで抽出する。"""
        t = datetime(2026, 5, 4, 13, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t,
            output=ObservationOutput(
                prose="誰かが近づいた。",
                structured={"actor": 501, "spot_id_value": 77},
                observation_category="social",
            ),
        )
        act = ActionResultEntry(
            occurred_at=t + timedelta(minutes=1),
            action_summary="話しかけた",
            result_summary="無視された。",
            tool_name="talk",
        )
        inp = build_chunk_encoding_input(PlayerId(9), (obs,), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert "entity:actor:501" in ep.who
        assert ep.location.spot_id == 77
        canon = {c.to_canonical() for c in ep.cues}
        assert "place_spot:77" in canon
        assert any(k.startswith("entity:") for k in canon)

    def test_overflow_observation_contributes_to_cues_not_timeline(self) -> None:
        """
        observation_overflow_from_window は unified には入らないが、
        cue / who / 場所ヒントの材料には含まれる。
        """
        t0 = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        overflow = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="溢れ",
                structured={"spot_id_value": 88},
                observation_category="environment",
            ),
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(hours=1),
            action_summary="行動",
            result_summary="結果",
            tool_name="noop",
        )
        inp = build_chunk_encoding_input(
            PlayerId(1),
            (),
            (act,),
            observation_overflow_from_window=(overflow,),
        )
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert "88" not in ep.observed  # タイムラインに観測行が無い
        assert ep.location.spot_id == 88
        assert any(c.to_canonical() == "place_spot:88" for c in ep.cues)

    def test_action_tool_field_joins_distinct_tools(self) -> None:
        """EpisodeAction.tool_name は複数 tool の辞書順連結。"""
        t = datetime(2026, 5, 4, 15, 0, 0, tzinfo=timezone.utc)
        acts = (
            ActionResultEntry(
                occurred_at=t,
                action_summary="a",
                result_summary="r",
                tool_name="beta",
            ),
            ActionResultEntry(
                occurred_at=t + timedelta(seconds=1),
                action_summary="b",
                result_summary="r",
                tool_name="alpha",
            ),
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), acts)
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.action is not None
        assert ep.action.tool_name == "alpha,beta"
