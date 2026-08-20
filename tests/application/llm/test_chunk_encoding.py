"""チャンクエンコード契約・バッファ同期のテスト"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    ChunkEncodingInput,
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
    format_action_result_line_for_recent_events,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.observation_short_term_memory_sync import (
    drain_observation_buffer_into_short_term_memory,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
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

    def test_failure_without_diagnostic_code_uses_only_world_words(self) -> None:
        """診断分類を持たない失敗は内部ラベルを補わず、本人向けの事実だけを出す。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="一瞬の空白",
            result_summary="意識が途切れ、この間の自分の行動を思い出せない。",
            success=False,
            error_code=None,
            tool_name="一瞬の空白",
        )

        text = format_action_result_line_for_recent_events(entry)

        assert text == (
            "[行動] 一瞬の空白 → [失敗] | "
            "意識が途切れ、この間の自分の行動を思い出せない。"
        )
        assert "error_code=" not in text
        assert "tool=" not in text

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

    def test_prediction_label_appears_between_action_and_result(self) -> None:
        """#552 PR-A: expected_result があれば [予測: ...] が行動と結果の間に出る。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="「古い祭壇」に対して調べるを行った",
            result_summary="石は冷たく、何も起きなかった。",
            success=True,
            expected_result="祭壇から封印の手がかりが得られる",
        )
        text = format_action_result_line_for_recent_events(entry)
        assert "[予測: 祭壇から封印の手がかりが得られる]" in text
        # 「行動 → 予測 → 結果」の順
        assert text.index("[行動]") < text.index("[予測:") < text.index("[結果]")

    def test_no_prediction_label_when_expected_result_absent(self) -> None:
        """#552 PR-A: expected_result が None なら [予測: ...] は出ない (露出 OFF の現状)。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="x を実行しました。",
            result_summary="成功。",
            success=True,
            expected_result=None,
        )
        assert "[予測:" not in format_action_result_line_for_recent_events(entry)

    def test_prediction_label_on_failure_line(self) -> None:
        """#552 PR-A: 失敗行にも [予測: ...] が付く (予測と実際のズレを読めるように)。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="扉を開けようとした",
            result_summary="鍵がかかっていた",
            success=False,
            error_code="BLOCKED",
            expected_result="扉が開くはず",
        )
        text = format_action_result_line_for_recent_events(entry)
        assert "[予測: 扉が開くはず]" in text
        assert "[失敗]" in text

    def test_prediction_label_on_omit_result_line(self) -> None:
        """#552 PR-A: omit_result (成功・結果省略) 行にも [予測: ...] は付く。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="speech_say を実行しました。",
            result_summary="発言しました。",
            success=True,
            omit_result_in_prompt=True,
            expected_result="相手が振り向く",
        )
        text = format_action_result_line_for_recent_events(entry)
        assert "[予測: 相手が振り向く]" in text
        assert "→ [結果]" not in text

    def test_inner_thought_is_rendered_once_as_own_line(self) -> None:
        """inner_thought は action_summary の JSON ではなく「心の声:」行に 1 回だけ出る。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary='look_around({"target_label":"周囲"}) を実行しました。',
            result_summary="失敗した",
            success=False,
            error_code="UNSUPPORTED_TOOL",
            inner_thought="周囲を見回したい。",
        )
        text = format_action_result_line_for_recent_events(entry)
        assert text.count("心の声:") == 1
        assert "心の声: 周囲を見回したい。" in text
        assert "inner_thought" not in text
        assert "【心の声】" not in text

    def test_speech_line_keeps_content_in_action_and_compact_audience_in_parentheses(
        self,
    ) -> None:
        """speak は発話本文を action 側に置き、結果行の重複した「発言した: X」は出さない。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="あなたは言った: 「北へ行く」",
            result_summary="（3 名に届いた）",
            success=True,
            tool_name=TOOL_NAME_SPEECH,
        )
        text = format_action_result_line_for_recent_events(entry)
        # 発話には呼び出し行を置かない。本文が伏せ字になるので情報が増えず、
        # 直前の行が「あなたは言った」と言っている以上、重複でもある。
        assert text == "[行動] あなたは言った: 「北へ行く」（3 名に届いた）"
        assert "→ [結果]" not in text

    def test_call_line_quotes_copyable_values_and_uses_free_text_placeholders(
        self,
    ) -> None:
        """完全一致値だけを引用し、自由文は引用符なしの日本語で書き方を示す。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="当番表へ書いた",
            result_summary="完了",
            success=True,
            tool_name="interact",
            identifier_arguments={
                "target_label": "当番表",
                "action_name": "write_note",
            },
            free_text_argument_names=("parameters",),
        )

        text = format_action_result_line_for_recent_events(entry)

        assert (
            '呼び出し: interact(target_label="当番表", '
            'action_name="write_note", parameters=本文)'
        ) in text
        assert '"本文"' not in text

    def test_call_line_preserves_quotes_inside_identifier_arrays(self) -> None:
        """配列内の完全一致値も JSON の引用符を保ち、そのまま写せる。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="二品を渡した",
            result_summary="完了",
            success=True,
            tool_name="give_item",
            identifier_arguments={
                "gives": '["火打ち石","流木"]',
                "target_player_label": "セナ",
            },
        )

        text = format_action_result_line_for_recent_events(entry)

        assert (
            '呼び出し: give_item(gives=["火打ち石","流木"], '
            'target_player_label="セナ")'
        ) in text

    def test_call_line_is_present_even_when_the_action_has_no_arguments(self) -> None:
        """成功した行動なら、引数が無くても呼び出し行を必ず出す。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="耳を澄ませた",
            result_summary="静かだった",
            success=True,
            tool_name="listen",
        )

        text = format_action_result_line_for_recent_events(entry)

        assert "呼び出し: listen()" in text

    def test_failed_call_does_not_repeat_rejected_arguments_as_an_example(
        self,
    ) -> None:
        """失敗した値は引用符つきの手本として履歴へ残さない。

        失敗行には ``error_code`` と復帰文があるため、呼び出し行が無い理由を
        推測させずに、通らなかった名前の自己強化だけを止められる。
        """
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="配膳用の裏口へ進もうとした",
            result_summary="対象の名前が見つかりません。",
            success=False,
            error_code="INVALID_TARGET_LABEL",
            tool_name="interact",
            identifier_arguments={
                "target_label": "配膳用の裏口",
                "action_name": "進む",
            },
        )

        text = format_action_result_line_for_recent_events(entry)

        assert "[失敗]" in text
        assert "error_code=INVALID_TARGET_LABEL" in text
        assert "呼び出し:" not in text
        assert 'action_name="進む"' not in text

    def test_appending_a_later_action_keeps_the_first_rendered_bytes(self) -> None:
        """後続行を足しても既存の呼び出し行は書き換わらず、接頭辞に残る。"""
        first = ActionResultEntry(
            occurred_at=datetime(2026, 8, 8, 6, 0),
            action_summary="当番表を読んだ",
            result_summary="確認した",
            success=True,
            tool_name="interact",
            identifier_arguments={"action_name": "read_board"},
        )
        later = ActionResultEntry(
            occurred_at=datetime(2026, 8, 8, 6, 1),
            action_summary="話した",
            result_summary="届いた",
            success=True,
            tool_name="speak",
            free_text_argument_names=("content",),
        )
        formatter = DefaultRecentEventsFormatter()

        before = formatter.format([], [first])
        after = formatter.format([], [first, later])

        assert after.startswith(before + "\n")
        # 見たいのは**接頭辞が書き換わらないこと**。呼び出し行そのものは
        # 発話では出さなくなったので、追記された行の中身で確かめる。
        assert "話した" in after
        assert "呼び出し: interact(" in before

    def test_speech_line_keeps_degraded_audience_counts(self) -> None:
        """speak の到達内訳は、ぼんやり / かすかが混ざる場合だけ短く残る。"""
        entry = ActionResultEntry(
            occurred_at=datetime.now(),
            action_summary="あなたは叫んだ: 「集合」",
            result_summary="（3 名に届いた。ぼんやり=1 / かすか=1）",
            success=True,
            tool_name=TOOL_NAME_SPEECH,
        )
        text = format_action_result_line_for_recent_events(entry)
        assert "ぼんやり=1 / かすか=1" in text
        assert "明瞭=" not in text

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
        overflow = drain_observation_buffer_into_short_term_memory(buf, win, pid)
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
        overflow = drain_observation_buffer_into_short_term_memory(buf, win, pid)
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
        overflow_helper = drain_observation_buffer_into_short_term_memory(buf, win, pid)
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
