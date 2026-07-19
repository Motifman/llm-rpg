"""U9b (予測誤差統一設計 部品5・想起の信用割り当て) — 的中側の record_recall_hits_if_applicable。

``_recall_prediction_outcome_stamping.record_recall_hits_if_applicable`` は
chunk 主観補完の完了点で「思い出したから当たった」を的中側 sidecar
(``IEpisodicRecallSuccessStore``) に還流する。U9a の
``stamp_recall_prediction_outcome_if_applicable`` (外れ側) と対称の
ガード条件を持つ。3 経路 (同期 coordinator / 非同期 scheduler 2 種) から
呼ばれる共通ロジックなので、ここでは関数単体として直接テストする。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from ai_rpg_world.application.llm.services._recall_prediction_outcome_stamping import (
    record_recall_hits_if_applicable,
)
from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    InMemoryEpisodicRecallSuccessStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
_BEING = BeingId("being_w1_p1")


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-current",
        player_id=1,
        occurred_at=_NOW,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="explore"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected="何か見つかるはず",
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


@dataclass(frozen=True)
class _StubAction:
    """``compute_chunk_attribution`` / ``prediction_context_ids_from_actions``

    が getattr で読む最小限の action stub。"""

    expected_result: Optional[str] = None
    prediction_context_id: Optional[str] = None
    in_context_belief_ids: Tuple[str, ...] = ()


def _seed_recall_buffer(
    buffer: InMemoryEpisodicRecallBufferStore,
    *,
    prediction_context_id: str,
    episode_id: str,
    recall_id: str = "r-1",
) -> None:
    buffer.append_by_being(
        _BEING,
        EpisodicRecallObservation(
            recall_id=recall_id,
            player_id=1,
            episode_id=episode_id,
            recalled_at=_NOW,
            source_axes=("temporal",),
            current_state_snapshot="state",
            recent_events_snapshot="events",
            persona_snapshot="persona",
            situation_cues=("cue",),
            turn_index=1,
            prediction_context_id=prediction_context_id,
        ),
    )


class TestRecordRecallHitsHappyPath:
    """flag ON + 全条件が揃ったときに hit が加算される。"""

    def test_expected_result_context_episode_hit_incremented(
        self,
    ) -> None:
        """的中 かつ expected result ありなら in context episode のhitが加算される。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 1

    def test_multiple_episode_same_prediction_context_id_all_incremented(
        self,
    ) -> None:
        """複数 episode が同じ predictioncontextid なら全件加算される。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer,
            prediction_context_id="pc-1",
            episode_id="ep-a",
            recall_id="r-a",
        )
        _seed_recall_buffer(
            buffer,
            prediction_context_id="pc-1",
            episode_id="ep-b",
            recall_id="r-b",
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-a") == 1
        assert success.get_hit_count_by_being(_BEING, "ep-b") == 1

    def test_calls_multiple(self) -> None:
        """複数回呼ばれると加算され続ける。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        actions = [
            _StubAction(expected_result="見つかるはず", prediction_context_id="pc-1")
        ]
        for _ in range(3):
            record_recall_hits_if_applicable(
                recall_buffer_store=buffer,
                recall_success_store=success,
                recall_hit_boost_enabled=True,
                being_id=_BEING,
                episode=_episode(prediction_error=None),
                chunk_actions=actions,
            )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 3


class TestRecordRecallHitsGuards:
    """安全な縮退条件 (= 導入前と一致) を保証する。"""

    def test_flag_off(self) -> None:
        """flag OFF なら加算しない。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=False,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_recall_buffer_store_unwired(self) -> None:
        """recall buffer store 未配線なら加算しない。"""
        success = InMemoryEpisodicRecallSuccessStore()
        record_recall_hits_if_applicable(
            recall_buffer_store=None,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_unwired_recall_success_store_completes_without_exception(self) -> None:
        """recall success store 未配線なら例外を投げず完了する。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        # 例外を投げないことのみ確認 (return 先を検証する store が無い)。
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=None,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )

    def test_being_id_unresolved(self) -> None:
        """being id 未解決なら加算しない。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=None,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_prediction_error_non_none(self) -> None:
        """prediction error が非Noneなら外れなので加算しない。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error="外れた: 実際は雨だった"),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_expected_result_action(
        self,
    ) -> None:
        """CONFIRMATION 転記 (U4) と同じ「水増しガード」。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(expected_result=None, prediction_context_id="pc-1")
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_prediction_context_id_off(
        self,
    ) -> None:
        """prediction context id が無ければ id機構OFFとして加算しない。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        _seed_recall_buffer(
            buffer, prediction_context_id="pc-1", episode_id="ep-source"
        )
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(expected_result="見つかるはず", prediction_context_id=None)
            ],
        )
        assert success.get_hit_count_by_being(_BEING, "ep-source") == 0

    def test_matches_recall_observation_not_incremented(self) -> None:
        """一致するrecall observationが無ければ何も加算されない。"""
        buffer = InMemoryEpisodicRecallBufferStore()
        success = InMemoryEpisodicRecallSuccessStore()
        # recall observation を seed しない = 想起無しで予測が当たったケース
        record_recall_hits_if_applicable(
            recall_buffer_store=buffer,
            recall_success_store=success,
            recall_hit_boost_enabled=True,
            being_id=_BEING,
            episode=_episode(prediction_error=None),
            chunk_actions=[
                _StubAction(
                    expected_result="見つかるはず", prediction_context_id="pc-1"
                )
            ],
        )
        assert success.list_all_by_being(_BEING) == {}
