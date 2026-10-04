"""本番 runtime の状態崩壊の証拠が、Being の解決を経て実際に積まれることを保証する。

needs decay stage と倒れた・起きたの handler は、runtime が組む
``_resolve_state_collapse_being_id`` で player_id から BeingId を引く。この
closure は例外を握られる位置にあるため、closure 自体が壊れていても run は
成功扱いのまま証拠だけが作られなくなる。stage や handler を単体で試す
テストは resolver を差し替えるので、この closure を通らない。
"""

from datetime import datetime, timezone
from pathlib import Path

from tests.runtime_config_helpers import episodic_config

from ai_rpg_world.application.world_runtime.world_runtime import (
    WorldRuntime,
    create_world_runtime,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent, PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2_short.json"
)


def _build_runtime() -> WorldRuntime:
    return create_world_runtime(
        _SCENARIO_PATH,
        config=episodic_config(
            belief_evidence_enabled=True,
            state_collapse_evidence_enabled=True,
        ),
    )


def _resolve_being_id(runtime: WorldRuntime, player_id: PlayerId) -> BeingId:
    being_id = runtime._aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, player_id
    )
    assert being_id is not None
    return being_id


def _put_anchor_episode(runtime: WorldRuntime, player_id: PlayerId, being_id: BeingId) -> None:
    assert runtime._episodic_stack is not None
    runtime._episodic_stack.episode_store.put_by_being(
        being_id,
        SubjectiveEpisode(
            episode_id="ep-anchor",
            player_id=player_id.value,
            being_id=being_id,
            occurred_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
            game_time_label=None,
            source=EpisodeSource(event_ids=("evt-1",)),
            location=EpisodeLocation(),
            action=EpisodeAction(tool_name="wait"),
            who=(),
            what="w",
            why=None,
            observed="o",
            expected=None,
            outcome="ok",
            prediction_error=None,
            felt=None,
            interpreted=None,
            cues=(),
        ),
    )


class TestStateCollapseEvidenceThroughRuntimeResolver:
    """runtime が組んだ Being 解決の closure を通して状態崩壊の証拠が積まれることを見る。"""

    def test_hunger_reaching_max_on_tick_appends_state_collapse_evidence(self) -> None:
        """空腹を上限まで上げた player で 1 tick 進めると、needs decay stage が
        その Being に「空腹が限界に達した。」の STATE_COLLAPSE の証拠を 1 件積む。"""
        runtime = _build_runtime()
        player_id = runtime.get_player_ids()[0]
        being_id = _resolve_being_id(runtime, player_id)
        _put_anchor_episode(runtime, player_id, being_id)
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        status.increase_need(NeedType.HUNGER, 100)
        runtime._player_status_repo.save(status)
        assert runtime._episodic_stack is not None
        buffer_store = runtime._episodic_stack.belief_evidence_buffer_store
        assert buffer_store is not None

        runtime.advance_tick()

        evidences = buffer_store.list_all_by_being(being_id)
        assert [e.source_kind for e in evidences] == [BeliefEvidenceSourceKind.STATE_COLLAPSE]
        assert evidences[0].text == "空腹が限界に達した。"

    def test_player_downed_by_starvation_appends_state_collapse_evidence(self) -> None:
        """HP 1 で空腹が上限の player が飢えで倒れると、「戦闘不能になった。」の
        STATE_COLLAPSE の証拠がその Being に積まれる。"""
        runtime = _build_runtime()
        player_id = runtime.get_player_ids()[0]
        being_id = _resolve_being_id(runtime, player_id)
        _put_anchor_episode(runtime, player_id, being_id)
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        status.apply_damage(status.hp.value - 1)
        status.increase_need(NeedType.HUNGER, 100)
        runtime._player_status_repo.save(status)
        assert runtime._episodic_stack is not None
        buffer_store = runtime._episodic_stack.belief_evidence_buffer_store
        assert buffer_store is not None

        runtime.advance_tick()

        downed = runtime._player_status_repo.find_by_id(player_id)
        assert downed is not None
        assert downed.is_down is True
        downed_evidences = [
            e for e in buffer_store.list_all_by_being(being_id) if e.text == "戦闘不能になった。"
        ]
        assert [e.source_kind for e in downed_evidences] == [BeliefEvidenceSourceKind.STATE_COLLAPSE]

    def test_revived_event_lets_next_down_append_another_evidence(self) -> None:
        """倒れた後に起きたイベントが届くと倒れた状態の記録が消え、次に倒れたとき
        「戦闘不能になった。」の証拠がもう 1 件積まれる。起きたイベントが Being を
        引けないと記録が残り、2 回目の証拠は積まれない。"""
        runtime = _build_runtime()
        player_id = runtime.get_player_ids()[0]
        being_id = _resolve_being_id(runtime, player_id)
        _put_anchor_episode(runtime, player_id, being_id)
        assert runtime._episodic_stack is not None
        buffer_store = runtime._episodic_stack.belief_evidence_buffer_store
        assert buffer_store is not None
        publisher = runtime._speech_event_publisher
        publisher.publish_all([PlayerDownedEvent.create(player_id, "PlayerStatusAggregate")])

        publisher.publish_all(
            [PlayerRevivedEvent.create(player_id, "PlayerStatusAggregate", hp_recovered=1, total_hp=100)]
        )
        publisher.publish_all([PlayerDownedEvent.create(player_id, "PlayerStatusAggregate")])

        downed_texts = [
            e.text for e in buffer_store.list_all_by_being(being_id) if e.text == "戦闘不能になった。"
        ]
        assert len(downed_texts) == 2
