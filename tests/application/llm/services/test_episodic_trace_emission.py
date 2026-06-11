"""``EpisodicChunkCoordinator`` と ``DefaultPromptBuilder`` の trace 記録
(Issue #283 後続)。

- chunk 書き込み時に ``TraceEventKind.EPISODIC_CHUNK_WRITTEN`` を emit
- passive recall 実行時に ``TraceEventKind.EPISODIC_RECALL`` を emit
- trace_recorder 未注入なら no-op
- recorder 例外は本来の処理を止めない
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    EpisodicCue,
    EpisodicCueSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.trace import (
    ITraceRecorder,
    NullTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture_trace(recorder: NullTraceRecorder) -> List:
    """NullTraceRecorder の record を wrap して capture list を返す。"""
    captured: List = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


def _make_episode(
    *,
    player_id: int = 1,
    episode_id: str = "smoke-ep-1",
    spot_id: int = 3,
    recall_text: str = "RECALL_TEXT_FOR_TEST",
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=spot_id),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(
            EpisodicCue(
                axis="place_spot",
                value=str(spot_id),
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        ),
        recall_text=recall_text,
    )


# ──────────────────────────────────────────────────────────────────
# EpisodicChunkCoordinator: chunk write の trace 記録
# ──────────────────────────────────────────────────────────────────


class TestChunkCoordinatorTraceEmission:
    """chunk 書き込み時に EPISODIC_CHUNK_WRITTEN が記録される。"""

    def _build_coord(self, *, recorder=None, tick: int = 5):
        buffer = DefaultObservationContextBuffer()
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        coord = EpisodicChunkCoordinator(
            observation_buffer=buffer,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            episodic_episode_store=episode_store,
            chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
            trace_recorder=recorder,
            current_tick_provider=lambda: tick,
        )
        return coord, buffer, action_store, episode_store

    def _trigger_chunk_close(
        self, coord, buffer, action_store, player_id: PlayerId
    ) -> None:
        """boundary を踏むのに必要な最小限を仕込む (PR #322 後続: MIN=3):

        - 2 件の wait (MIN ゲート積み上げ)
        - その間に salient 観測 (breaks_movement=True; PR #322 で schedules_turn 単独は salient ではない)
        - 3 件目の action を ``scene_boundary=True`` で投入 → SCENE_BOUNDARY_ACTION で確実にクローズ
        """
        t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        action_store.append(
            player_id,
            action_summary="wait1",
            result_summary="ok",
            occurred_at=t0,
            occurred_tick=0,
        )
        coord.after_action_recorded(player_id)
        # salient 観測 (PR #322 後続: breaks_movement=True を使う)
        buffer.append(
            player_id,
            ObservationEntry(
                occurred_at=datetime(2026, 5, 1, 12, 0, 30, tzinfo=timezone.utc),
                output=ObservationOutput(
                    prose="salient event",
                    structured={"type": "x"},
                    observation_category="social",
                    breaks_movement=True,
                ),
                game_time_label=None,
            ),
        )
        action_store.append(
            player_id,
            action_summary="wait2",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc),
            occurred_tick=1,
        )
        coord.after_action_recorded(player_id)
        # 3 件目: scene_boundary=True で確実に SCENE_BOUNDARY_ACTION 経路でクローズ
        action_store.append(
            player_id,
            action_summary="move",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc),
            occurred_tick=2,
            scene_boundary=True,
        )
        coord.after_action_recorded(player_id)

    def test_recorder_注入_かつ_chunk_close_で_event_が_emit(self) -> None:
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        coord, buffer, action_store, episode_store = self._build_coord(recorder=recorder)
        pid = PlayerId(1)
        self._trigger_chunk_close(coord, buffer, action_store, pid)
        # episode は書かれた
        assert len(episode_store.list_recent(pid.value, 10)) > 0
        # chunk_written event が 1 件以上
        chunk_events = [
            e for e in captured if e.kind == TraceEventKind.EPISODIC_CHUNK_WRITTEN
        ]
        assert len(chunk_events) == 1
        ev = chunk_events[0]
        assert ev.player_id == 1
        assert ev.tick == 5
        # payload にエピソード ID / cue / boundary reason が乗る
        assert ev.payload["episode_id"]
        assert ev.payload["boundary_reason"]  # "observation_salient" 等
        assert isinstance(ev.payload["cues"], list)
        assert ev.payload["action_count"] >= 1
        assert ev.payload["observation_count"] >= 1

    def test_recorder_未注入なら_event_は_emit_されない(self) -> None:
        coord, buffer, action_store, _ = self._build_coord(recorder=None)
        pid = PlayerId(1)
        # ただ実行できることだけ確認 (recorder lookup が None なので no-op)
        self._trigger_chunk_close(coord, buffer, action_store, pid)

    def test_naive_と_aware_の_datetime_が混在しても_TypeError_を投げない(self) -> None:
        """tz-naive と tz-aware の occurred_at が混在しても chunk 書き込みが成功する。

        第20回実験で 48/50 件の chunk write が
        ``TypeError: can't compare offset-naive and offset-aware datetimes`` で
        失敗していた。供給源 (HeartbeatObservationEmitter は aware、
        escape_game runtime は当時 naive) の不一致が原因。境界で正規化されて
        いることを担保する regression test。
        """
        coord, buffer, action_store, episode_store = self._build_coord(recorder=None)
        pid = PlayerId(1)
        # action store は (修正後の escape_game runtime と同じく) aware で統一
        action_store.append(
            pid,
            action_summary="wait1",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        )
        coord.after_action_recorded(pid)
        # observation buffer に naive 観測が一つでも紛れ込むと
        # 修正前は obs_slice の比較で TypeError になっていた。
        buffer.append(
            pid,
            ObservationEntry(
                occurred_at=datetime(2026, 5, 1, 12, 0, 30),  # naive (regression source)
                output=ObservationOutput(
                    prose="naive obs",
                    structured={"type": "x"},
                    observation_category="social",
                    schedules_turn=True,
                ),
                game_time_label=None,
            ),
        )
        action_store.append(
            pid,
            action_summary="wait2",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc),
        )
        coord.after_action_recorded(pid)
        # PR #322 後続: MIN=3 を満たすため scene_boundary action を追加。
        # ここで chunk が SCENE_BOUNDARY_ACTION 経由でクローズ。修正前は
        # sort/filter のどこかで TypeError になっていた。
        action_store.append(
            pid,
            action_summary="move",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc),
            scene_boundary=True,
        )
        coord.after_action_recorded(pid)
        # chunk write が完走したことを episode_store の有無で確認
        assert len(episode_store.list_recent(pid.value, 10)) > 0

    def test_obs_slice_に_naive_と_aware_が_複数件混在しても_sort_で_落ちない(self) -> None:
        """``obs_slice`` の sort key も _as_utc で正規化されている (Issue #311 後続)。

        Issue #295 r2 fix (#309) は filter 比較を _as_utc で守ったが、その直後の
        sort key が raw occurred_at を使っていたため、obs_slice に 2 件以上の
        混在 entry が含まれると TypeError で chunk write が失敗していた。
        第21回 r1 で 21/30 chunk write 失敗の真因。
        """
        coord, buffer, action_store, episode_store = self._build_coord(recorder=None)
        pid = PlayerId(1)
        action_store.append(
            pid,
            action_summary="wait1",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        )
        coord.after_action_recorded(pid)
        # 同一 chunk 範囲に **複数件** 観測を入れる。1 件目は naive、2 件目は aware。
        # 修正前は obs_slice = [naive_obs, aware_obs] の sort で落ちる。
        buffer.append(
            pid,
            ObservationEntry(
                occurred_at=datetime(2026, 5, 1, 12, 0, 20),  # naive
                output=ObservationOutput(
                    prose="naive obs 1",
                    structured={"type": "x"},
                    observation_category="social",
                    schedules_turn=True,
                ),
                game_time_label=None,
            ),
        )
        buffer.append(
            pid,
            ObservationEntry(
                # aware (= heartbeat / action_failed が発行するパターン)
                occurred_at=datetime(2026, 5, 1, 12, 0, 40, tzinfo=timezone.utc),
                output=ObservationOutput(
                    prose="aware obs 2",
                    structured={"type": "y"},
                    observation_category="social",
                ),
                game_time_label=None,
            ),
        )
        action_store.append(
            pid,
            action_summary="wait2",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc),
        )
        coord.after_action_recorded(pid)
        # PR #322 後続: MIN=3 を満たす scene_boundary action を追加。
        # 修正前はここで TypeError (sort key で naive と aware を比較)。
        action_store.append(
            pid,
            action_summary="move",
            result_summary="ok",
            occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc),
            scene_boundary=True,
        )
        coord.after_action_recorded(pid)
        assert len(episode_store.list_recent(pid.value, 10)) > 0

    def test_recorder_例外は_chunk_書き込みを止めない(self) -> None:
        """recorder.record が例外を投げても episode は store に書かれる。"""

        class _BrokenRecorder(ITraceRecorder):
            def record(self, kind, **kw):
                raise RuntimeError("trace io fail")

            def close(self):
                pass

        coord, buffer, action_store, episode_store = self._build_coord(
            recorder=_BrokenRecorder()
        )
        pid = PlayerId(1)
        self._trigger_chunk_close(coord, buffer, action_store, pid)
        # trace 失敗でも episode は書かれている
        assert len(episode_store.list_recent(pid.value, 10)) > 0


# ──────────────────────────────────────────────────────────────────
# DefaultPromptBuilder: passive recall の trace 記録
# ──────────────────────────────────────────────────────────────────


class TestPromptBuilderRecallTraceEmission:
    """passive recall 実行ごとに EPISODIC_RECALL が記録される。"""

    def test_recall_時に_候補と_situation_cues_が_event_に乗る(self) -> None:
        """builder._emit_episodic_recall_trace を直接駆動して payload を検証
        (full prompt build を経由しない最小ユニットテスト)。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        # 最小限の core で builder インスタンスを作る。重要なのは内部メソッド
        # _emit_episodic_recall_trace の挙動なので、本格的 build は省略する。
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = recorder
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda: 42

        ep = _make_episode(episode_id="recall-ep-1", recall_text="長いリコール本文..." * 10)
        from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
            EpisodicPassiveRecallCandidate,
        )
        cand = EpisodicPassiveRecallCandidate(
            episode=ep, source_axes=("place_spot", "temporal")
        )
        cue = EpisodicCue(
            axis="place_spot", value="3", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        builder._emit_episodic_recall_trace(
            player_id=PlayerId(7),
            situation_cues=(cue,),
            candidates=[cand],
        )

        events = [e for e in captured if e.kind == TraceEventKind.EPISODIC_RECALL]
        assert len(events) == 1
        ev = events[0]
        assert ev.player_id == 7
        assert ev.tick == 42
        assert ev.payload["situation_cues"] == ["place_spot:3"]
        assert ev.payload["candidate_count"] == 1
        # candidates payload に必須キーが揃う
        cand0 = ev.payload["candidates"][0]
        assert cand0["episode_id"] == "recall-ep-1"
        assert "place_spot" in cand0["source_axes"]
        # recall_text snippet は 120 文字に切り詰められている
        assert len(cand0["recall_text_snippet"]) <= 120
        assert cand0["recall_text_snippet"].startswith("長いリコール本文")
        # relevant_memories_text を渡さない既定では chars_total=0
        assert ev.payload["recall_text_chars_total"] == 0

    def test_recall_text_chars_total_に_実注入テキスト長が乗る(self) -> None:
        """relevant_memories_text を渡すと、その文字数が payload に出る
        (post-hoc に prompt_tokens 比へ換算するための計測点)。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = recorder
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda: 1

        joined = "おれは昨日この場所で罠を仕掛けた。\n仲間が崖から落ちるのを見た。"
        builder._emit_episodic_recall_trace(
            player_id=PlayerId(1),
            situation_cues=(),
            candidates=[],
            relevant_memories_text=joined,
        )

        events = [e for e in captured if e.kind == TraceEventKind.EPISODIC_RECALL]
        assert len(events) == 1
        assert events[0].payload["recall_text_chars_total"] == len(joined)

    def test_recorder_未注入なら_emit_は_no_op(self) -> None:
        """trace_recorder=None なら例外なく no-op。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = None
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda: 0

        cue = EpisodicCue(
            axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        # 例外なく完走
        builder._emit_episodic_recall_trace(
            player_id=PlayerId(1),
            situation_cues=(cue,),
            candidates=[],
        )

    def test_provider_経由_遅延注入された_recorder_に追従(self) -> None:
        """trace_recorder_provider が後から非 None を返せばその recorder に
        emit される。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        holder = {"r": None}

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = None
        builder._trace_recorder_provider = lambda: holder["r"]
        builder._current_tick_provider = lambda: 0

        cue = EpisodicCue(
            axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        # 1 回目: provider が None → 記録されない
        builder._emit_episodic_recall_trace(
            player_id=PlayerId(1), situation_cues=(cue,), candidates=[]
        )
        assert captured == []

        # provider 経由で recorder 差し込み
        holder["r"] = recorder
        builder._emit_episodic_recall_trace(
            player_id=PlayerId(1), situation_cues=(cue,), candidates=[]
        )
        assert len(captured) == 1


class TestPromptBuilderSectionBreakdownTraceEmission:
    """``_emit_prompt_section_breakdown_trace`` が section 別 char 数を払い出す
    (実験 #356 後続: prefix cache 分析用)。"""

    def test_section_別_char_数が_event_に乗る(self) -> None:
        """各 section のテキスト長が独立に payload に乗る。token ではなく char。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = recorder
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda: 7

        tools = [
            {"type": "function", "function": {"name": "wait", "description": "待つ", "parameters": {}}},
            {"type": "function", "function": {"name": "move", "description": "移動する", "parameters": {}}},
        ]
        builder._emit_prompt_section_breakdown_trace(
            player_id=PlayerId(3),
            system_content="SYSTEM" * 10,           # 60
            objective_text="目的目的目的",          # 6
            current_state_text="現在地表示",         # 5
            active_memos_text="メモ",                # 2
            recent_events_text="出来事" * 20,       # 60
            relevant_memories_text="記憶" * 5,      # 10
            inventory_text="持ち物",                # 3
            instruction="指示文",                   # 3
            tools=tools,
            user_content="USER_BODY" * 5,           # 45
        )

        events = [e for e in captured if e.kind == TraceEventKind.PROMPT_SECTION_BREAKDOWN]
        assert len(events) == 1
        p = events[0].payload
        assert events[0].tick == 7
        assert events[0].player_id == 3
        assert p["system_chars"] == 60
        assert p["objective_chars"] == 6
        assert p["current_state_chars"] == 5
        assert p["memos_chars"] == 2
        assert p["recent_events_chars"] == 60
        assert p["recall_chars"] == 10
        assert p["inventory_chars"] == 3
        assert p["instruction_chars"] == 3
        assert p["user_content_chars"] == 45
        assert p["messages_total_chars"] == 60 + 45
        assert p["tools_count"] == 2
        # tools は json.dumps の長さで近似される (>0 で十分)
        assert p["tools_chars"] > 0

    def test_recorder_未注入なら_section_breakdown_emit_は_no_op(self) -> None:
        """trace_recorder=None でも例外なく完走 (prompt 構築を止めない)。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = None
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda: 0
        builder._emit_prompt_section_breakdown_trace(
            player_id=PlayerId(1),
            system_content="",
            objective_text="",
            current_state_text="",
            active_memos_text="",
            recent_events_text="",
            relevant_memories_text="",
            inventory_text="",
            instruction="",
            tools=[],
            user_content="",
        )


# ──────────────────────────────────────────────────────────────────
# End-to-end: escape_game runtime で trace が出る
# ──────────────────────────────────────────────────────────────────


class TestEscapeGameEpisodicTraceE2E:
    """env=1 で trace_recorder を runtime に差し込んで実行すると、chunk
    write と recall の両方が trace event として記録される。"""

    def test_smoke_run_で_chunk_written_と_recall_イベントが_両方_emit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        scenario_path = (
            Path(__file__).resolve().parents[4]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_escape_game_runtime(scenario_path)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        runtime.set_trace_recorder(recorder)

        # 既存の smoke と同じ最小シーケンスで chunk と recall を発火させる
        kaito_id, rin_id = runtime.get_player_ids()[0], runtime.get_player_ids()[1]
        # PR #322 後続: MIN_ACTIONS_FOR_CLOSE=3 + scene_boundary 経路に合わせて拡張
        runtime.do_move(rin_id, "entrance_hall")  # リン → カイト同 spot
        runtime.do_wait(kaito_id)                  # action 1
        runtime.do_speech(rin_id, "カイト、こんにちは", SpeechChannel.SAY)
        runtime.do_wait(kaito_id)                  # action 2
        runtime.do_move(kaito_id, "reading_room")  # action 3 (scene_boundary) → close
        # recall を発動するため prompt を 1 度組む
        runtime.build_full_prompt(kaito_id)

        chunk_events = [
            e for e in captured if e.kind == TraceEventKind.EPISODIC_CHUNK_WRITTEN
        ]
        recall_events = [
            e for e in captured if e.kind == TraceEventKind.EPISODIC_RECALL
        ]
        assert len(chunk_events) > 0, "chunk_written 未発火 — write 経路の trace が動いていない"
        assert len(recall_events) > 0, "recall 未発火 — recall 経路の trace が動いていない"
