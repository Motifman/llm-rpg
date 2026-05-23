"""チャンクエンコード契約・バッファ同期のテスト"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    ChunkEncodingInput,
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.observation_sliding_window_sync import (
    drain_observation_buffer_into_sliding_window,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestMergeObservationsAndActionResultsToUnifiedTimeline:
    """統一タイムラインのマージ・整形（RecentEventsFormatter と同一規則）"""

    def test_chronological_oldest_first_matches_formatter_order(self) -> None:
        """occurred_at 昇順となり DefaultRecentEventsFormatter の行順と一致する"""
        base = datetime(2025, 1, 1, 12, 0, 0)
        obs_oldest = ObservationEntry(
            occurred_at=base,
            output=ObservationOutput(
                prose="最も古い観測です。",
                structured={},
                observation_category="environment",
            ),
        )
        action_middle = ActionResultEntry(
            occurred_at=base + timedelta(minutes=5),
            action_summary="move を実行",
            result_summary="移動した。",
        )
        obs_newest = ObservationEntry(
            occurred_at=base + timedelta(minutes=10),
            output=ObservationOutput(
                prose="最も新しい観測です。",
                structured={},
                observation_category="environment",
            ),
        )
        observations = [obs_newest, obs_oldest]
        action_results = [action_middle]
        timeline = merge_observations_and_action_results_to_unified_timeline(
            observations, action_results
        )
        formatter = DefaultRecentEventsFormatter()
        text_from_formatter = formatter.format(observations, action_results)
        text_from_timeline = format_unified_timeline_as_recent_events_bullets(timeline)
        assert text_from_formatter == text_from_timeline
        assert len(timeline) == 3
        assert "最も古い観測です。" in timeline[0].text
        assert timeline[1].kind == "action_result"
        assert "最も新しい観測です。" in timeline[2].text

    def test_game_time_label_on_observation(self) -> None:
        """観測の game_time_label が行頭に付く"""
        t = datetime(2025, 2, 1, 9, 0, 0)
        obs = ObservationEntry(
            occurred_at=t,
            output=ObservationOutput(
                prose="朝",
                structured={},
                observation_category="environment",
            ),
            game_time_label="1年1月1日 朝",
        )
        lines = merge_observations_and_action_results_to_unified_timeline([obs], [])
        assert len(lines) == 1
        assert lines[0].text == "[1年1月1日 朝] 朝"

    def test_action_failure_line_matches_formatter(self) -> None:
        """失敗行動の行がフォーマッタと一致する"""
        failed = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary='x({"a":1}) を実行しました。',
            result_summary="失敗。理由 対処: 直せ",
            success=False,
            error_code="BAD_ARG",
            tool_name="foo_tool",
            should_reschedule=True,
        )
        timeline = merge_observations_and_action_results_to_unified_timeline([], [failed])
        fmt = DefaultRecentEventsFormatter()
        assert fmt.format([], [failed]) == format_unified_timeline_as_recent_events_bullets(
            timeline
        )
        assert "[失敗]" in timeline[0].text
        assert "error_code=BAD_ARG" in timeline[0].text

    def test_action_line_with_game_time_label(self) -> None:
        """Issue #188: action_result に game_time_label があれば観測と
        同じ ``[時刻] [行動] ...`` の prefix が付く。"""
        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            format_action_result_line_for_recent_events,
        )

        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="speech_say を実行しました。",
            result_summary="発言しました。",
            success=True,
            game_time_label="深夜 0:20",
        )
        text = format_action_result_line_for_recent_events(entry)
        assert text.startswith("[深夜 0:20] [行動] ")
        assert "→ [結果] 発言しました。" in text

    def test_action_line_without_game_time_label_is_backward_compat(self) -> None:
        """game_time_label 未指定なら従来通り ``[行動]`` 始まり (時刻 prefix なし)。"""
        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            format_action_result_line_for_recent_events,
        )

        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="x を実行しました。",
            result_summary="成功。",
            success=True,
        )
        text = format_action_result_line_for_recent_events(entry)
        # 時刻 prefix が無い = 先頭が `[行動]` (時刻なしの従来形式)
        assert text.startswith("[行動] x")
        assert "[行動]" in text
        # 時刻 prefix 「[XX:YY]」のような時刻形式 prefix が無いことを別の手段で確認
        assert " [行動]" not in text  # スペース + [行動] は時刻 prefix がある時に発生

    def test_action_line_omit_result_when_success(self) -> None:
        """Issue #188: omit_result_in_prompt=True かつ success=True なら
        ``→ [結果] ...`` 部分を省略する (speech_say の result ノイズ削減)。"""
        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            format_action_result_line_for_recent_events,
        )

        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary='speech_say({"content": "Hi"}) を実行しました。',
            result_summary="発言しました。",
            success=True,
            omit_result_in_prompt=True,
        )
        text = format_action_result_line_for_recent_events(entry)
        # → [結果] が出ない
        assert "→ [結果]" not in text
        assert "発言しました。" not in text
        # action_summary は出る
        assert "speech_say" in text
        assert "Hi" in text

    def test_action_line_omit_result_ignored_on_failure(self) -> None:
        """失敗時は omit_result_in_prompt=True でも error_code / 対処を出す
        (LLM が修正できるよう情報を保つ)。"""
        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            format_action_result_line_for_recent_events,
        )

        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary='speech_say を実行しました。',
            result_summary="失敗。content は必須",
            success=False,
            error_code="INVALID_ARGUMENT",
            omit_result_in_prompt=True,
        )
        text = format_action_result_line_for_recent_events(entry)
        assert "[失敗]" in text
        assert "error_code=INVALID_ARGUMENT" in text

    def test_action_line_omit_result_with_time_label(self) -> None:
        """time_label と omit_result_in_prompt を同時に使ったとき:
        ``[時刻] [行動] {summary}`` の形になる。"""
        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            format_action_result_line_for_recent_events,
        )

        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary='speech_say({"content": "yo"}) を実行しました。',
            result_summary="発言しました。",
            success=True,
            game_time_label="0:30",
            omit_result_in_prompt=True,
        )
        text = format_action_result_line_for_recent_events(entry)
        assert text.startswith("[0:30] [行動] ")
        assert "→ [結果]" not in text

    def test_naive_and_utc_aware_unified_timeline_sorted_without_type_error(
        self,
    ) -> None:
        """occurred_at が naive / aware 混在でも timestamp 昇順へ並べ、TypeError にならない。"""
        utc = timezone.utc
        obs_naive = ObservationEntry(
            occurred_at=datetime(2025, 8, 1, 14, 0, 0),
            output=ObservationOutput(
                prose="na",
                structured={},
                observation_category="environment",
            ),
        )
        obs_utc = ObservationEntry(
            occurred_at=datetime(2025, 8, 2, 0, 0, 0, tzinfo=utc),
            output=ObservationOutput(
                prose="utc",
                structured={},
                observation_category="environment",
            ),
        )
        timeline = merge_observations_and_action_results_to_unified_timeline(
            [obs_utc, obs_naive], ()
        )
        assert len(timeline) == 2
        stamps = tuple(line.occurred_at.timestamp() for line in timeline)
        assert stamps == tuple(sorted(stamps))


class TestChunkEncodingInput:
    """ChunkEncodingInput の検証とエピソード起動ゲート"""

    def test_build_chunk_encoding_input_mismatch_timeline_raises(self) -> None:
        """unified_timeline がマージ結果と一致しない ChunkEncodingInput は拒否される"""
        obs = ObservationEntry(
            occurred_at=datetime(2025, 1, 1, 0, 0, 0),
            output=ObservationOutput(
                prose="a", structured={}, observation_category="self_only"
            ),
        )
        with pytest.raises(ValueError, match="unified_timeline"):
            ChunkEncodingInput(
                player_id=PlayerId(1),
                observations=(obs,),
                action_results=(),
                unified_timeline=(),
            )

    def test_episode_generation_requires_action(self) -> None:
        """行動結果が 0 件ならエピソード生成不可"""
        inp = build_chunk_encoding_input(
            PlayerId(1),
            (),
            (),
        )
        assert chunk_encoding_episode_generation_allowed(inp) is False

    def test_episode_generation_allowed_with_action(self) -> None:
        """行動結果が 1 件以上なら起動可"""
        act = ActionResultEntry(
            occurred_at=datetime(2025, 1, 1, 0, 0, 0),
            action_summary="m",
            result_summary="r",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        assert chunk_encoding_episode_generation_allowed(inp) is True


class TestDrainObservationBufferIntoSlidingWindow:
    """観測 drain → append_all が PromptBuilder と同順序であること"""

    def test_empty_buffer_returns_empty_overflow(self) -> None:
        """drain が空なら append せず空リスト"""
        buf = DefaultObservationContextBuffer()
        win: DefaultSlidingWindowMemory = DefaultSlidingWindowMemory(max_entries_per_player=10)
        pid = PlayerId(1)
        overflow = drain_observation_buffer_into_sliding_window(buf, win, pid)
        assert overflow == []
        assert win.get_recent(pid, 10) == []

    def test_drain_appends_and_returns_overflow(self) -> None:
        """複数件 drain しウィンドウ上限を超えた分が overflow になる"""
        buf = DefaultObservationContextBuffer()
        win = DefaultSlidingWindowMemory(max_entries_per_player=2)
        pid = PlayerId(1)
        t0 = datetime(2025, 1, 1, 0, 0, 0)
        entries = [
            ObservationEntry(
                occurred_at=t0,
                output=ObservationOutput(
                    prose=f"e{i}", structured={}, observation_category="self_only"
                ),
            )
            for i in range(3)
        ]
        for e in entries:
            buf.append(pid, e)
        overflow = drain_observation_buffer_into_sliding_window(buf, win, pid)
        assert len(overflow) == 1
        assert overflow[0].output.prose == "e0"
        recent = win.get_recent(pid, 10)
        assert len(recent) == 2
        texts = {r.output.prose for r in recent}
        assert texts == {"e1", "e2"}

    def test_matches_prompt_builder_sequence(self) -> None:
        """DefaultPromptBuilder の drain→append_all 節と同一の観測列・溢れになる"""
        buf = DefaultObservationContextBuffer()
        win = DefaultSlidingWindowMemory(max_entries_per_player=3)
        pid = PlayerId(1)
        for i in range(5):
            buf.append(
                pid,
                ObservationEntry(
                    occurred_at=datetime(2025, 1, 1, 0, 0, i),
                    output=ObservationOutput(
                        prose=f"p{i}", structured={}, observation_category="self_only"
                    ),
                ),
            )
        overflow_helper = drain_observation_buffer_into_sliding_window(buf, win, pid)
        buf2 = DefaultObservationContextBuffer()
        win2 = DefaultSlidingWindowMemory(max_entries_per_player=3)
        for i in range(5):
            buf2.append(
                pid,
                ObservationEntry(
                    occurred_at=datetime(2025, 1, 1, 0, 0, i),
                    output=ObservationOutput(
                        prose=f"p{i}", structured={}, observation_category="self_only"
                    ),
                ),
            )
        drained = buf2.drain(pid)
        overflow_pb = win2.append_all(pid, drained) if drained else []
        assert overflow_helper == overflow_pb
        assert win.get_recent(pid, 10) == win2.get_recent(pid, 10)
