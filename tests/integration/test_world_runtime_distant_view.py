"""常時遠景が current state prompt にだけ入る実配線を保証する。"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.being.experiment_snapshot_session import (
    _default_world_subsystem_codecs,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from tests.runtime_config_helpers import episodic_config, runtime_config


_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_V3 = _SCENARIOS_DIR / "survival_island_v3_coop.json"
_V4 = _SCENARIOS_DIR / "survival_island_v4_coop.json"


class _TraceRecorderSpy:
    """record() の呼び出しを保持する最小 spy。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, *, tick=None, player_id=None, **payload):  # noqa: ANN001
        self.events.append(
            (
                str(kind),
                {"tick": tick, "player_id": player_id, **payload},
            )
        )

    def close(self) -> None:
        pass


class _TurnSchedulerSpy:
    """schedules_turn の伝播を記録する最小 spy。"""

    def __init__(self) -> None:
        self.calls: list[tuple[PlayerId, bool]] = []

    def maybe_schedule(self, player_id: PlayerId, output) -> None:  # noqa: ANN001
        self.calls.append((player_id, bool(output.schedules_turn)))


class TestDistantViewRuntimePrompt:
    """create_world_runtime から build_llm_context までの遠景 prompt 配線。"""

    def test_v4_initial_prompt_renders_distant_view_without_area_id(self) -> None:
        """v4 の初期浜辺では山影と森が現在地説明直後に出て、area_id は出ない。"""
        runtime = create_world_runtime(_V4, config=runtime_config())

        text = runtime.build_llm_context(PlayerId(1)).current_state_text

        assert "北東の遠くに切り立った山影が見える。" in text
        assert "北に深い森の緑が見える。" in text
        assert "mountain" not in text
        assert "forest" not in text
        assert "area_id" not in text

        lines = text.splitlines()
        description_index = next(
            i for i, line in enumerate(lines) if line.startswith("  嵐で打ち上げられた")
        )
        assert lines[description_index + 1] == "  北東の遠くに切り立った山影が見える。"

    def test_scenario_without_areas_keeps_distant_view_empty(self) -> None:
        """areas 未定義の既存シナリオでは常時遠景を出さず、現行 prompt を汚さない。"""
        runtime = create_world_runtime(_V3, config=runtime_config())

        text = runtime.build_llm_context(PlayerId(1)).current_state_text

        assert "北東の遠くに切り立った山影が見える。" not in text
        assert "遠景:" not in text

    def test_distant_view_is_prompt_only_and_not_written_to_observation_or_episode(
        self,
    ) -> None:
        """遠景は prompt にだけ出て、recent observation と episode 記憶を汚さない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        player_id = PlayerId(1)
        distant_phrase = "北東の遠くに切り立った山影が見える。"

        text = runtime.build_llm_context(player_id).current_state_text

        assert distant_phrase in text
        recent_observations = runtime._obs_buffer.get_observations(player_id)
        recent_observation_text = "\n".join(
            getattr(entry.output, "prose", "") for entry in recent_observations
        )
        assert distant_phrase not in recent_observation_text

        stack = runtime._episodic_stack
        assert stack is not None
        episodes = stack.episode_store.list_recent_by_being(
            BeingId("being_w1_p1"),
            limit=20,
        )
        episode_text = "\n".join(
            f"{episode.title}\n{episode.summary}\n{episode.recall_text}"
            for episode in episodes
        )
        assert distant_phrase not in episode_text

    def test_v4_signal_smoke_replaces_mountain_area_after_object_state_lit(self) -> None:
        """signal_fire_pit.state.lit=true になると、同方角の山影ではなく白い煙が遠景に出る。"""
        runtime = create_world_runtime(_V4, config=runtime_config())

        before = runtime.build_llm_context(PlayerId(1)).current_state_text
        _set_signal_fire_lit(runtime, True)
        after = runtime.build_llm_context(PlayerId(1)).current_state_text

        assert "北東の遠くに切り立った山影が見える。" in before
        assert "北東の山の方に白い煙が見える。" not in before
        assert "北東の山の方に白い煙が見える。" in after
        assert "北東の遠くに切り立った山影が見える。" not in after
        assert "summit_signal_smoke" not in after
        assert "signal_fire_pit" not in after
        assert "mountain" not in after

    def test_active_cue_from_current_area_is_excluded_from_distant_view(self) -> None:
        """cue の origin area が現在地なら、遠景ではなく局所説明の領分として除外する。"""
        runtime = create_world_runtime(_V4, config=runtime_config())
        _set_signal_fire_lit(runtime, True)

        summit_player = PlayerId(1)
        _teleport_player(runtime, int(summit_player.value), "summit")
        text = runtime.build_llm_context(summit_player).current_state_text

        assert "白い煙が見える" not in text

    def test_active_cue_is_prompt_only_and_not_written_to_observation_or_episode(self) -> None:
        """動的 cue の常時遠景も prompt にだけ出て、recent observation と episode 記憶を汚さない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        player_id = PlayerId(1)
        cue_phrase = "北東の山の方に白い煙が見える。"
        _set_signal_fire_lit(runtime, True)

        text = runtime.build_llm_context(player_id).current_state_text

        assert cue_phrase in text
        recent_observations = runtime._obs_buffer.get_observations(player_id)
        recent_observation_text = "\n".join(
            getattr(entry.output, "prose", "") for entry in recent_observations
        )
        assert cue_phrase not in recent_observation_text

        stack = runtime._episodic_stack
        assert stack is not None
        episodes = stack.episode_store.list_recent_by_being(
            BeingId("being_w1_p1"),
            limit=20,
        )
        episode_text = "\n".join(
            f"{episode.title}\n{episode.summary}\n{episode.recall_text}"
            for episode in episodes
        )
        assert cue_phrase not in episode_text


class TestDistantViewRuntimeTrace:
    """現在状態系の遠景 trace が既定で出ず、明示時だけ出ることを固定する。"""

    def test_trace_is_not_recorded_by_default(self) -> None:
        """DISTANT_VIEW_TRACE_ENABLED が false なら prompt build 時に遠景 trace は出ない。"""
        runtime = create_world_runtime(_V4, config=runtime_config())
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_llm_context(PlayerId(1))

        kinds = [kind for kind, _ in recorder.events]
        assert TraceEventKind.DISTANT_VIEW_RENDERED not in kinds
        assert TraceEventKind.DISTANT_VIEW_SKIPPED not in kinds

    def test_trace_records_rendered_payload_when_enabled(self) -> None:
        """trace 有効時は rendered area と閾値を構造化 payload に残す。"""
        runtime = create_world_runtime(
            _V4,
            config=runtime_config(distant_view_trace_enabled=True),
        )
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_llm_context(PlayerId(1))

        events = [
            payload
            for kind, payload in recorder.events
            if kind == TraceEventKind.DISTANT_VIEW_RENDERED
        ]
        assert len(events) == 1
        payload = events[0]
        assert payload["player_id"] == 1
        assert payload["rendered_area_ids"] == ["mountain", "forest"]
        assert payload["rendered_cue_ids"] == []
        assert payload["active_cue_count"] == 0
        assert payload["rendered_count"] == 2
        assert payload["thresholds"]["score"] == 0.20

    def test_trace_records_rendered_cue_ids_when_active_cue_is_rendered(self) -> None:
        """trace 有効時は表示された cue id と active cue 件数を構造化 payload に残す。"""
        runtime = create_world_runtime(
            _V4,
            config=runtime_config(distant_view_trace_enabled=True),
        )
        _set_signal_fire_lit(runtime, True)
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_llm_context(PlayerId(1))

        events = [
            payload
            for kind, payload in recorder.events
            if kind == TraceEventKind.DISTANT_VIEW_RENDERED
        ]
        assert len(events) == 1
        payload = events[0]
        assert payload["rendered_area_ids"] == ["forest"]
        assert payload["rendered_cue_ids"] == ["summit_signal_smoke"]
        assert payload["active_cue_count"] == 1
        assert payload["rendered_count"] == 2

    def test_trace_records_skipped_reason_when_cue_source_object_is_missing(
        self,
        caplog,
    ) -> None:
        """cue の source object が runtime で解決不能なら、警告ログと trace に理由を残す。"""
        runtime = create_world_runtime(
            _V4,
            config=runtime_config(distant_view_trace_enabled=True),
        )
        summit_id = SpotId(runtime.id_mapper.get_int("spot", "summit"))
        object_id = SpotObjectId.create(runtime.id_mapper.get_int("object", "signal_fire_pit"))
        interior = runtime._spot_interior_repo.find_by_spot_id(summit_id)
        assert interior is not None
        runtime._spot_interior_repo.save(
            summit_id,
            type(interior)(
                sub_locations=interior.sub_locations,
                objects=tuple(
                    obj for obj in interior.objects if obj.object_id != object_id
                ),
                ground_items=interior.ground_items,
                discoverable_items=interior.discoverable_items,
            ),
        )
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        with caplog.at_level(logging.WARNING):
            runtime.build_llm_context(PlayerId(1))

        payload = next(
            payload
            for kind, payload in recorder.events
            if kind == TraceEventKind.DISTANT_VIEW_RENDERED
        )
        assert "cue_source_object_missing" in payload["skipped_reasons"]
        assert "distant cue source object is missing" in caplog.text


class TestDistantCueAppearanceRuntime:
    """動的 cue の false→true 境界だけが観測として配達されることを保証する。"""

    def test_false_to_true_delivers_once_and_records_trace(self) -> None:
        """狼煙 cue は false→true 境界で見える player へ1回だけ届き、継続 true では再発火しない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        recorder = _TraceRecorderSpy()
        scheduler = _TurnSchedulerSpy()
        runtime.set_trace_recorder(recorder)
        runtime._observation_turn_scheduler = scheduler
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()
        runtime._evaluate_distant_cue_appearances()

        observations = _distant_cue_observations(runtime, PlayerId(1))
        assert len(observations) == 1
        output = observations[0].output
        assert output.prose == "北東の山の方から白い煙が上がった。"
        assert output.observation_category == "environment"
        assert output.schedules_turn is True
        assert output.breaks_movement is False
        assert output.structured == {
            "type": "distant_cue_appeared",
            "cue_id": "summit_signal_smoke",
            "visible_name": "白い煙",
            "origin_area_id": "mountain",
            "direction": "北東",
            "distance_band": "far",
        }

        changed = _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_STATE_CHANGED)
        delivered = _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_DELIVERED)
        assert len(changed) == 1
        assert changed[0]["cue_id"] == "summit_signal_smoke"
        assert changed[0]["old_active"] is False
        assert changed[0]["new_active"] is True
        assert changed[0]["visible_recipient_count"] == 4
        assert len(delivered) == 4
        assert scheduler.calls
        assert {scheduled for _, scheduled in scheduler.calls} == {True}

    def test_initial_true_is_baseline_and_does_not_deliver(self) -> None:
        """初回評価時点ですでに true の cue は baseline として記録し、出現観測を配らない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()

        assert _distant_cue_observations(runtime, PlayerId(1)) == []
        assert _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_STATE_CHANGED) == []
        assert runtime._distant_cue_states["summit_signal_smoke"] == {
            "active": True,
            "initialized": True,
            "last_changed_tick": None,
        }

    def test_delivers_only_to_players_who_can_see_the_origin_area(self) -> None:
        """屋内・現在地 area・隣接 area の player には遠景出現観測を配らない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        _teleport_player(runtime, 2, "summit")
        _teleport_player(runtime, 3, "foothills")
        _teleport_player(runtime, 4, "cave_inner")
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()

        assert len(_distant_cue_observations(runtime, PlayerId(1))) == 1
        assert _distant_cue_observations(runtime, PlayerId(2)) == []
        assert _distant_cue_observations(runtime, PlayerId(3)) == []
        assert _distant_cue_observations(runtime, PlayerId(4)) == []

    def test_appear_event_observation_enters_observation_history(self) -> None:
        """出現イベントは ambient ではなく観測なので、prompt build で直近出来事に入る。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        player_id = PlayerId(1)
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)
        runtime._evaluate_distant_cue_appearances()

        prompt = runtime.build_full_prompt(player_id)
        user_message = prompt["messages"][1]["content"]

        assert "北東の山の方から白い煙が上がった。" in user_message
        recent = runtime._sliding_window.get_recent(player_id, 20)
        assert any(
            entry.output.structured.get("type") == "distant_cue_appeared"
            for entry in recent
        )

    def test_restored_active_true_state_does_not_fire_again(self) -> None:
        """snapshot restore 後に active=true と復元された cue は同じ出現を再発火しない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        _set_signal_fire_lit(runtime, True)
        _restore_distant_cue_state(
            runtime,
            {
                "schema_version": 1,
                "entries": [
                    {
                        "cue_id": "summit_signal_smoke",
                        "active": True,
                        "initialized": True,
                        "last_changed_tick": 7,
                    }
                ],
            },
        )

        runtime._evaluate_distant_cue_appearances()

        assert _distant_cue_observations(runtime, PlayerId(1)) == []

    def test_cue_without_appear_event_tracks_state_without_delivery_or_trace(self) -> None:
        """appear_event 未指定 cue は境界状態だけを追い、観測配達と state_changed trace は出さない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        cue = runtime.scenario.distant_cues[0]
        runtime.scenario = replace(
            runtime.scenario,
            distant_cues=(
                type(cue)(
                    cue_id=cue.cue_id,
                    source=cue.source,
                    origin_area_id=cue.origin_area_id,
                    visible_name=cue.visible_name,
                    prominence=cue.prominence,
                    ambient_descriptions=cue.ambient_descriptions,
                    appear_event=None,
                ),
            ),
        )
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()

        assert runtime._distant_cue_states["summit_signal_smoke"]["active"] is True
        assert _distant_cue_observations(runtime, PlayerId(1)) == []
        assert _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_STATE_CHANGED) == []

    def test_no_visible_recipients_still_records_state_changed_trace(self) -> None:
        """誰にも見えない false→true でも、trace に visible_recipient_count=0 を残す。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)
        for player_id in (1, 2, 3, 4):
            _teleport_player(runtime, player_id, "summit")
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()

        changed = _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_STATE_CHANGED)
        assert len(changed) == 1
        assert changed[0]["visible_recipient_count"] == 0
        assert changed[0]["delivery_skipped_reason"] == "no_visible_recipients"
        assert _trace_payloads(recorder, TraceEventKind.DISTANT_CUE_DELIVERED) == []

    def test_missing_source_object_records_debug_skipped_reason(self, caplog) -> None:
        """境界検出側でも source object 解決不能を警告ログと debug trace に残す。"""
        runtime = create_world_runtime(
            _V4,
            config=runtime_config(distant_view_trace_enabled=True),
        )
        summit_id = SpotId(runtime.id_mapper.get_int("spot", "summit"))
        object_id = SpotObjectId.create(runtime.id_mapper.get_int("object", "signal_fire_pit"))
        interior = runtime._spot_interior_repo.find_by_spot_id(summit_id)
        assert interior is not None
        runtime._spot_interior_repo.save(
            summit_id,
            type(interior)(
                sub_locations=interior.sub_locations,
                objects=tuple(
                    obj for obj in interior.objects if obj.object_id != object_id
                ),
                ground_items=interior.ground_items,
                discoverable_items=interior.discoverable_items,
            ),
        )
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        with caplog.at_level(logging.WARNING):
            runtime._evaluate_distant_cue_appearances()

        payloads = _trace_payloads(recorder, TraceEventKind.DISTANT_VIEW_SKIPPED)
        assert len(payloads) == 1
        assert payloads[0]["cue_id"] == "summit_signal_smoke"
        assert payloads[0]["skipped_reasons"] == ["cue_source_object_missing"]
        assert "distant cue source object is missing" in caplog.text

    def test_event_prose_does_not_leak_internal_ids_and_fixed_message_works(self) -> None:
        """出現観測本文には cue_id/object_id/area_id を出さず、placeholder 無し固定文も使える。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        cue = runtime.scenario.distant_cues[0]
        runtime.scenario = replace(
            runtime.scenario,
            distant_cues=(
                type(cue)(
                    cue_id=cue.cue_id,
                    source=cue.source,
                    origin_area_id=cue.origin_area_id,
                    visible_name=cue.visible_name,
                    prominence=cue.prominence,
                    ambient_descriptions=cue.ambient_descriptions,
                    appear_event=type(cue.appear_event)(
                        message="山の方から煙が上がった。",
                        schedules_turn=False,
                    ),
                ),
            ),
        )
        scheduler = _TurnSchedulerSpy()
        runtime._observation_turn_scheduler = scheduler
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime._evaluate_distant_cue_appearances()

        output = _distant_cue_observations(runtime, PlayerId(1))[0].output
        assert output.prose == "山の方から煙が上がった。"
        assert "summit_signal_smoke" not in output.prose
        assert "signal_fire_pit" not in output.prose
        assert "mountain" not in output.prose
        assert scheduler.calls
        assert {scheduled for _, scheduled in scheduler.calls} == {False}

    def test_post_tick_detection_fires_after_tick_driven_source_change(self) -> None:
        """毎 tick の post-tick 検出で、interact 以外の state 変化も恒久的に取りこぼさない。"""
        runtime = create_world_runtime(_V4, config=episodic_config())
        runtime._evaluate_distant_cue_appearances()
        _set_signal_fire_lit(runtime, True)

        runtime.advance_tick()

        assert len(_distant_cue_observations(runtime, PlayerId(1))) == 1


def _set_signal_fire_lit(runtime, lit: bool) -> None:  # noqa: ANN001
    summit_id = SpotId(runtime.id_mapper.get_int("spot", "summit"))
    object_id = SpotObjectId.create(runtime.id_mapper.get_int("object", "signal_fire_pit"))
    interior = runtime._spot_interior_repo.find_by_spot_id(summit_id)
    assert interior is not None
    obj = interior.get_object(object_id)
    assert obj is not None
    runtime._spot_interior_repo.save(
        summit_id,
        interior.replace_object(obj.with_state({**obj.state, "lit": lit})),
    )


def _teleport_player(runtime, player_id: int, spot_id: str) -> None:  # noqa: ANN001
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(player_id)
    spot = SpotId.create(runtime.id_mapper.get_int("spot", spot_id))
    try:
        graph.unplace_entity(entity_id)
    except Exception:
        pass
    graph.place_entity(entity_id, spot)
    runtime._spot_graph_repo.save(graph)


def _distant_cue_observations(runtime, player_id: PlayerId):  # noqa: ANN001, ANN201
    return [
        entry
        for entry in runtime._obs_buffer.get_observations(player_id)
        if entry.output.structured.get("type") == "distant_cue_appeared"
    ]


def _trace_payloads(recorder: _TraceRecorderSpy, kind: str) -> list[dict[str, Any]]:
    return [payload for event_kind, payload in recorder.events if event_kind == kind]


def _restore_distant_cue_state(runtime, data: dict[str, Any]) -> None:  # noqa: ANN001
    codec = next(
        codec
        for codec in _default_world_subsystem_codecs()
        if codec.subsystem_key == "distant_cue_state"
    )
    codec.restore(runtime, data)
