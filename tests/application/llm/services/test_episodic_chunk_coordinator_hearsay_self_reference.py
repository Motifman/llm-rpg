"""EpisodicChunkCoordinator の同期経路での heard_claims 自己言及フィルタ (H-2)。

H-2 (自己言及ループ / 横断レビュー): heard_claims の話者が聞き手本人かどうかを
ペルソナ文字列の解析 (LLM 依存) ではなく、``player_name_provider`` から取った
``actor_name`` との文字列一致で判定する。本テストは coordinator が実際に
``player_name_provider`` を解決し、``merge_llm_subjective_fields`` に actor_name を
渡すところまでの end-to-end 配線を保証する (unit レベルの正規化ロジック自体は
``test_episodic_chunk_subjective_fields_hearsay.py`` で検証済み)。

非同期経路 (scheduler) の対応テストは
``test_episodic_subjective_completion_schedulers.py`` にある。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
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
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
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
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)

_PLAYER_NAME = "カイト"


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    """chunk 主観補完 LLM のスタブ。固定の JSON を返すだけ (実 LLM 呼び出しなし)。"""

    def __init__(self, returns: dict[str, Any]) -> None:
        self._returns = returns

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._returns


def _build_coord(*, player_name_provider):
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    being_id = BeingProvisioningService(being_repo).ensure_attached(PlayerId(1))
    port = _StubPort(
        {
            "interpreted": "I",
            "recall_text": "R",
            "heard_claims": [
                {"speaker": _PLAYER_NAME, "claim": "自分の発言"},
                {"speaker": "リオ", "claim": "北の泉は安全だ"},
            ],
        }
    )
    subjective_service = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
    coord = EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        chunk_subjective_fields_service=subjective_service,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
        player_name_provider=player_name_provider,
    )
    return coord, buffer, action_store, episode_store, being_id


def _trigger_chunk_close(coord, buffer, action_store, player_id: PlayerId) -> None:
    """境界を踏んで chunk を確実に close する (MIN=3 ゲート + scene_boundary)。"""
    t0 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    action_store.append(
        player_id, action_summary="wait1", result_summary="ok", occurred_at=t0
    )
    coord.after_action_recorded(player_id)
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
    )
    coord.after_action_recorded(player_id)
    action_store.append(
        player_id,
        action_summary="move",
        result_summary="ok",
        occurred_at=datetime(2026, 5, 1, 12, 2, tzinfo=timezone.utc),
        scene_boundary=True,
    )
    coord.after_action_recorded(player_id)


class TestEpisodicChunkCoordinatorHearsaySelfReferenceSyncPath:
    """同期 LLM 補完経路 (chunk_subjective_fields_service 注入時) の自己言及フィルタ。"""

    def test_player_name_provider_self_speaker_claim_rejected(self) -> None:
        """player name provider あれば本人speakerのclaimが弾かれる。"""
        coord, buffer, action_store, episode_store, being_id = _build_coord(
            player_name_provider=lambda pid: _PLAYER_NAME,
        )
        player_id = PlayerId(1)

        _trigger_chunk_close(coord, buffer, action_store, player_id)

        episodes = episode_store.list_recent_by_being(being_id, limit=10)
        assert len(episodes) == 1
        speakers = [c.speaker for c in episodes[0].heard_claims]
        assert speakers == ["リオ"]

    def test_player_name_provider_unwired_self_speaker(self) -> None:
        """provider が None のときは自己判定を行わず、安全側 (縮退) に倒れる

        (persona_block_provider と同じ「未配線なら従来通り」規約)。
        """
        coord, buffer, action_store, episode_store, being_id = _build_coord(
            player_name_provider=None,
        )
        player_id = PlayerId(1)

        _trigger_chunk_close(coord, buffer, action_store, player_id)

        episodes = episode_store.list_recent_by_being(being_id, limit=10)
        assert len(episodes) == 1
        speakers = [c.speaker for c in episodes[0].heard_claims]
        assert speakers == [_PLAYER_NAME, "リオ"]


class TestEpisodicChunkCoordinatorInitValidation:
    """player_name_provider の型ガード (persona_block_provider と同じ規約)。"""

    def test_player_name_provider_callable_raises_type_error(self) -> None:
        """player name provider が callable でなければ TypeError。"""
        import pytest

        buffer = DefaultObservationContextBuffer()
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError, match="player_name_provider"):
            EpisodicChunkCoordinator(
                observation_buffer=buffer,
                sliding_window_memory=sliding,
                action_result_store=action_store,
                episodic_episode_store=episode_store,
                chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
                player_name_provider="not-callable",  # type: ignore[arg-type]
            )
