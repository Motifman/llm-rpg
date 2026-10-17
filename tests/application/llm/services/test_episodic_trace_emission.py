"""``EpisodicChunkCoordinator`` と ``DefaultPromptBuilder`` の trace 記録
(Issue #283 後続)。

- chunk 書き込み時に ``TraceEventKind.EPISODIC_CHUNK_WRITTEN`` を emit
- prompt 組み立てごとに ``TraceEventKind.PROMPT_SECTION_BREAKDOWN`` を emit
- trace_recorder 未注入なら no-op
- recorder 例外は本来の処理を止めない
"""
from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_id import BeingId as _MIG_BeingId

being_id = _MIG_BeingId('being_w1_p1')
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import EpisodicChunkCoordinator
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.services.observation_context_buffer import DefaultObservationContextBuffer
from ai_rpg_world.application.trace import ITraceRecorder, NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture_trace(recorder: NullTraceRecorder) -> list:
    """NullTraceRecorder の record を wrap して capture list を返す。"""
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev
    recorder.record = wrapper
    return captured

def _make_episode(*, player_id: int=1, episode_id: str='smoke-ep-1', spot_id: int=3, recall_text: str='RECALL_TEXT_FOR_TEST') -> SubjectiveEpisode:
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=BeingId(f'being_w1_p{player_id}'), occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc), game_time_label=None, source=EpisodeSource(event_ids=('evt-1',)), location=EpisodeLocation(spot_id=spot_id), action=EpisodeAction(tool_name='t'), who=('p',), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted=None, cues=(EpisodicCue(axis='place_spot', value=str(spot_id), source=EpisodicCueSource.RUNTIME_CONTEXT),), recall_text=recall_text)

class TestChunkCoordinatorTraceEmission:
    """chunk 書き込み時に EPISODIC_CHUNK_WRITTEN が記録される。"""

    def _build_coord(self, *, recorder=None, tick: int=5, chunk_subjective_fields_service=None):
        from ai_rpg_world.application.being.being_attachment_resolver import BeingAttachmentResolver
        from ai_rpg_world.application.being.being_provisioning_service import BeingProvisioningService
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository
        buffer = DefaultObservationContextBuffer()
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(being_repo)
        BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
        coord = EpisodicChunkCoordinator(observation_buffer=buffer, short_term_memory=sliding, action_result_store=action_store, episodic_episode_store=episode_store, chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(), chunk_subjective_fields_service=chunk_subjective_fields_service, trace_recorder=recorder, current_tick_provider=lambda : tick)
        return (coord, buffer, action_store, episode_store)

    def _trigger_chunk_close(self, coord, buffer, action_store, player_id: PlayerId, being_id) -> None:
        """boundary を踏むのに必要な最小限を仕込む (PR #322 後続: MIN=3):

        - 2 件の wait (MIN ゲート積み上げ)
        - その間に salient 観測 (breaks_movement=True; PR #322 で schedules_turn 単独は salient ではない)
        - 3 件目の action を ``scene_boundary=True`` で投入 → SCENE_BOUNDARY_ACTION で確実にクローズ
        """
        t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        action_store.append(player_id, action_summary='wait1', result_summary='ok', occurred_at=t0, occurred_tick=0)
        coord.after_action_recorded(player_id, being_id)
        buffer.append(player_id, ObservationEntry(occurred_at=datetime(2026, 5, 1, 12, 0, 30, tzinfo=timezone.utc), output=ObservationOutput(prose='salient event', structured={'type': 'x'}, observation_category='social', breaks_movement=True), game_time_label=None))
        action_store.append(player_id, action_summary='wait2', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc), occurred_tick=1)
        coord.after_action_recorded(player_id, being_id)
        action_store.append(player_id, action_summary='move', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc), occurred_tick=2, scene_boundary=True)
        coord.after_action_recorded(player_id, being_id)

    def test_recorder_chunk_close_event_emit(self) -> None:
        """recorder 注入 かつ chunk close で event が emit。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        (coord, buffer, action_store, episode_store) = self._build_coord(recorder=recorder)
        pid = PlayerId(1)
        self._trigger_chunk_close(coord, buffer, action_store, pid, being_id)
        assert len(episode_store.list_recent_by_being(being_id, 10)) > 0
        chunk_events = [e for e in captured if e.kind == TraceEventKind.EPISODIC_CHUNK_WRITTEN]
        assert len(chunk_events) == 1
        ev = chunk_events[0]
        assert ev.player_id == 1
        assert ev.tick == 5
        assert ev.payload['episode_id']
        assert ev.payload['boundary_reason']
        assert isinstance(ev.payload['cues'], list)
        assert ev.payload['action_count'] >= 1
        assert ev.payload['observation_count'] >= 1

    def test_recorder_uninjected_event_emit(self) -> None:
        """recorder 未注入なら event は emit されない。"""
        (coord, buffer, action_store, _) = self._build_coord(recorder=None)
        pid = PlayerId(1)
        self._trigger_chunk_close(coord, buffer, action_store, pid, being_id)

    def test_naive_aware_datetime_raises_type_error(self) -> None:
        """tz-naive と tz-aware の occurred_at が混在しても chunk 書き込みが成功する。

        第20回実験で 48/50 件の chunk write が
        ``TypeError: can't compare offset-naive and offset-aware datetimes`` で
        失敗していた。供給源 (HeartbeatObservationEmitter は aware、
        world_runtime runtime は当時 naive) の不一致が原因。境界で正規化されて
        いることを担保する regression test。
        """
        (coord, buffer, action_store, episode_store) = self._build_coord(recorder=None)
        pid = PlayerId(1)
        action_store.append(pid, action_summary='wait1', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))
        coord.after_action_recorded(pid, being_id)
        buffer.append(pid, ObservationEntry(occurred_at=datetime(2026, 5, 1, 12, 0, 30), output=ObservationOutput(prose='naive obs', structured={'type': 'x'}, observation_category='social', schedules_turn=True), game_time_label=None))
        action_store.append(pid, action_summary='wait2', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc))
        coord.after_action_recorded(pid, being_id)
        action_store.append(pid, action_summary='move', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc), scene_boundary=True)
        coord.after_action_recorded(pid, being_id)
        assert len(episode_store.list_recent_by_being(being_id, 10)) > 0

    def test_obs_slice_naive_aware_multiple_sort_does_not_crash(self) -> None:
        """``obs_slice`` の sort key も _as_utc で正規化されている (Issue #311 後続)。

        Issue #295 r2 fix (#309) は filter 比較を _as_utc で守ったが、その直後の
        sort key が raw occurred_at を使っていたため、obs_slice に 2 件以上の
        混在 entry が含まれると TypeError で chunk write が失敗していた。
        第21回 r1 で 21/30 chunk write 失敗の真因。
        """
        (coord, buffer, action_store, episode_store) = self._build_coord(recorder=None)
        pid = PlayerId(1)
        action_store.append(pid, action_summary='wait1', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))
        coord.after_action_recorded(pid, being_id)
        buffer.append(pid, ObservationEntry(occurred_at=datetime(2026, 5, 1, 12, 0, 20), output=ObservationOutput(prose='naive obs 1', structured={'type': 'x'}, observation_category='social', schedules_turn=True), game_time_label=None))
        buffer.append(pid, ObservationEntry(occurred_at=datetime(2026, 5, 1, 12, 0, 40, tzinfo=timezone.utc), output=ObservationOutput(prose='aware obs 2', structured={'type': 'y'}, observation_category='social'), game_time_label=None))
        action_store.append(pid, action_summary='wait2', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 1, tzinfo=timezone.utc))
        coord.after_action_recorded(pid, being_id)
        action_store.append(pid, action_summary='move', result_summary='ok', occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc), scene_boundary=True)
        coord.after_action_recorded(pid, being_id)
        assert len(episode_store.list_recent_by_being(being_id, 10)) > 0

    def test_recorder_chunk_raises_exception(self) -> None:
        """recorder.record が例外を投げても episode は store に書かれる。"""

        class _BrokenRecorder(ITraceRecorder):

            def record(self, kind, **kw):
                raise RuntimeError('trace io fail')

            def close(self):
                pass
        (coord, buffer, action_store, episode_store) = self._build_coord(recorder=_BrokenRecorder())
        pid = PlayerId(1)
        self._trigger_chunk_close(coord, buffer, action_store, pid, being_id)
        assert len(episode_store.list_recent_by_being(being_id, 10)) > 0

class TestPromptBuilderSectionBreakdownTraceEmission:
    """``_emit_prompt_section_breakdown_trace`` が section 別 char 数を払い出す
    (実験 #356 後続: prefix cache 分析用)。"""

    def test_section_different_char_event_included(self) -> None:
        """各 section のテキスト長が独立に payload に乗る。token ではなく char。"""
        from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = recorder
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda : 7
        tools = [{'type': 'function', 'function': {'name': 'wait', 'description': '待つ', 'parameters': {}}}, {'type': 'function', 'function': {'name': 'move', 'description': '移動する', 'parameters': {}}}]
        builder._emit_prompt_section_breakdown_trace(player_id=PlayerId(3), system_content='SYSTEM' * 10, objective_text='目的目的目的', current_state_text='現在地表示', memos_text='メモ', recent_events_text='出来事' * 20, inventory_text='持ち物', instruction='指示文', tools=tools, user_content='USER_BODY' * 5)
        events = [e for e in captured if e.kind == TraceEventKind.PROMPT_SECTION_BREAKDOWN]
        assert len(events) == 1
        p = events[0].payload
        assert events[0].tick == 7
        assert events[0].player_id == 3
        assert p['system_chars'] == 60
        assert p['objective_chars'] == 6
        assert p['current_state_chars'] == 5
        assert p['memos_chars'] == 2
        assert 'prediction_feedback_chars' not in p
        assert p['recent_events_chars'] == 60
        assert 'recall_chars' not in p
        assert p['inventory_chars'] == 3
        assert p['instruction_chars'] == 3
        assert p['user_content_chars'] == 45
        assert p['messages_total_chars'] == 60 + 45
        assert p['tools_count'] == 2
        assert p['tools_chars'] > 0

    def test_recorder_uninjected_section_breakdown_emit_op(self) -> None:
        """trace_recorder=None でも例外なく完走 (prompt 構築を止めない)。"""
        from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
        builder = object.__new__(DefaultPromptBuilder)
        builder._trace_recorder = None
        builder._trace_recorder_provider = None
        builder._current_tick_provider = lambda : 0
        builder._emit_prompt_section_breakdown_trace(player_id=PlayerId(1), system_content='', objective_text='', current_state_text='', memos_text='', recent_events_text='', inventory_text='', instruction='', tools=[], user_content='')

class TestWorldRuntimeEpisodicTraceE2E:
    """env=1 で trace_recorder を runtime に差し込んで実行すると、chunk
    write が trace event として記録される。"""

    def test_smoke_run_emits_chunk_written(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """smoke run で chunk written イベントが emit され、受動想起のイベントは出ない。"""
        from pathlib import Path

        from tests.runtime_config_helpers import episodic_config

        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
        scenario_path = Path(__file__).resolve().parents[4] / 'data' / 'scenarios' / 'forbidden_library_demo.json'
        runtime = create_world_runtime(scenario_path, config=episodic_config())
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        runtime.set_trace_recorder(recorder)
        (kaito_id, rin_id) = (runtime.get_player_ids()[0], runtime.get_player_ids()[1])
        runtime.do_move(rin_id, 'entrance_hall')
        runtime.do_explore(kaito_id)
        runtime.do_speech(rin_id, 'カイト、こんにちは', SpeechChannel.SAY)
        runtime.do_explore(kaito_id)
        runtime.do_move(kaito_id, 'reading_room')
        runtime.build_full_prompt(kaito_id)
        chunk_events = [e for e in captured if e.kind == TraceEventKind.EPISODIC_CHUNK_WRITTEN]
        assert len(chunk_events) > 0, 'chunk_written 未発火 — write 経路の trace が動いていない'
        assert not [e for e in captured if e.kind == 'episodic_recall']
