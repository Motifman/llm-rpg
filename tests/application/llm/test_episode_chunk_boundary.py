"""episode_chunk_boundary: チャンク閉鎖・エピソード起動タイミングの判定"""

from __future__ import annotations

from datetime import datetime, timedelta

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.episode_chunk_boundary import (
    ChunkBoundaryObservationHints,
    EpisodeChunkBoundaryDecision,
    EpisodeChunkBoundaryPolicy,
    decide_episode_chunk_boundary,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _action(t: datetime) -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=t,
        action_summary="tool を実行",
        result_summary="完了",
    )


class TestDecideEpisodeChunkBoundary:
    """ChunkEncodingInput とヒントから CLOSE / DEFER を決める"""

    def test_no_action_defers(self) -> None:
        """行動結果が 0 件ならエピソード経路に進まず DEFER"""
        obs = ObservationEntry(
            occurred_at=datetime(2026, 5, 1, 12, 0, 0),
            output=ObservationOutput(
                prose="環境",
                structured={},
                observation_category="environment",
            ),
        )
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), ())
        v = decide_episode_chunk_boundary(inp)
        assert v.decision == EpisodeChunkBoundaryDecision.DEFER
        assert v.reason_code == "no_action_in_interval"
        assert v.interval_end_occurred_at is None

    def test_action_only_closes_with_cursor(self) -> None:
        """行動のみのチャンクは CLOSE・カーソルは統一タイムライン末尾の occurred_at"""
        base = datetime(2026, 5, 2, 10, 0, 0)
        act = _action(base)
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        v = decide_episode_chunk_boundary(inp)
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "action_only_chunk"
        assert v.interval_end_occurred_at == base

    def test_drain_hint_threshold_triggers_close(self) -> None:
        """drain 件数が policy しきい値以上なら CLOSE（理由 drain_hint_threshold）"""
        base = datetime(2026, 5, 3, 8, 0, 0)
        obs = ObservationEntry(
            occurred_at=base,
            output=ObservationOutput(
                prose="同カテゴリ続き",
                structured={"k": 1},
                observation_category="self_only",
            ),
        )
        act = _action(base + timedelta(minutes=1))
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        policy = EpisodeChunkBoundaryPolicy(
            drained_observations_close_threshold=2,
            close_when_allowed_without_observation_boundary_signal=False,
        )
        v = decide_episode_chunk_boundary(
            inp,
            observation_hints=ChunkBoundaryObservationHints(drained_observation_entry_count=2),
            policy=policy,
        )
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "drain_hint_threshold"

    def test_observation_count_cap(self) -> None:
        """チャンク内観測件数が上限に達したら CLOSE"""
        base = datetime(2026, 5, 4, 9, 0, 0)
        observations = tuple(
            ObservationEntry(
                occurred_at=base + timedelta(seconds=i),
                output=ObservationOutput(
                    prose=f"o{i}",
                    structured={},
                    observation_category="self_only",
                ),
            )
            for i in range(3)
        )
        act = _action(base + timedelta(minutes=10))
        inp = build_chunk_encoding_input(PlayerId(1), observations, (act,))
        policy = EpisodeChunkBoundaryPolicy(
            max_observations_in_chunk_before_close=3,
            close_when_allowed_without_observation_boundary_signal=False,
        )
        v = decide_episode_chunk_boundary(inp, policy=policy)
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "observation_count_cap"

    def test_category_shift_closes(self) -> None:
        """先頭と末尾で observation_category が変われば CLOSE"""
        base = datetime(2026, 5, 5, 11, 0, 0)
        observations = (
            ObservationEntry(
                occurred_at=base,
                output=ObservationOutput(
                    prose="自分",
                    structured={},
                    observation_category="self_only",
                ),
            ),
            ObservationEntry(
                occurred_at=base + timedelta(minutes=1),
                output=ObservationOutput(
                    prose="他者",
                    structured={},
                    observation_category="social",
                ),
            ),
        )
        act = _action(base + timedelta(minutes=2))
        inp = build_chunk_encoding_input(PlayerId(1), observations, (act,))
        policy = EpisodeChunkBoundaryPolicy(close_when_allowed_without_observation_boundary_signal=False)
        v = decide_episode_chunk_boundary(inp, policy=policy)
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "observation_category_shift"

    def test_structured_keys_shift_consecutive(self) -> None:
        """連続する観測間で structured のキー集合が変われば CLOSE"""
        base = datetime(2026, 5, 6, 14, 0, 0)
        observations = (
            ObservationEntry(
                occurred_at=base,
                output=ObservationOutput(
                    prose="a",
                    structured={"x": 1},
                    observation_category="environment",
                ),
            ),
            ObservationEntry(
                occurred_at=base + timedelta(minutes=1),
                output=ObservationOutput(
                    prose="b",
                    structured={"y": 2},
                    observation_category="environment",
                ),
            ),
        )
        act = _action(base + timedelta(minutes=2))
        inp = build_chunk_encoding_input(PlayerId(1), observations, (act,))
        policy = EpisodeChunkBoundaryPolicy(close_when_allowed_without_observation_boundary_signal=False)
        v = decide_episode_chunk_boundary(inp, policy=policy)
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "structured_keys_shift"

    def test_defer_when_strict_policy_and_no_signal(self) -> None:
        """観測がありシグナルが無いとき、厳格 policy では DEFER"""
        base = datetime(2026, 5, 7, 16, 0, 0)
        obs = ObservationEntry(
            occurred_at=base,
            output=ObservationOutput(
                prose="単独観測",
                structured={"same": True},
                observation_category="self_only",
            ),
        )
        act = _action(base + timedelta(minutes=1))
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        policy = EpisodeChunkBoundaryPolicy(close_when_allowed_without_observation_boundary_signal=False)
        v = decide_episode_chunk_boundary(inp, policy=policy)
        assert v.decision == EpisodeChunkBoundaryDecision.DEFER
        assert v.reason_code == "no_boundary_signal_with_observations"

    def test_default_policy_closes_with_observations_without_signal(self) -> None:
        """既定 policy はエピソード起動可なら観測だけでも chunk_ready_default で CLOSE"""
        base = datetime(2026, 5, 8, 7, 0, 0)
        obs = ObservationEntry(
            occurred_at=base,
            output=ObservationOutput(
                prose="単独観測",
                structured={},
                observation_category="self_only",
            ),
        )
        act = _action(base + timedelta(minutes=1))
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        v = decide_episode_chunk_boundary(inp)
        assert v.decision == EpisodeChunkBoundaryDecision.CLOSE_FOR_EPISODE_ENCODING
        assert v.reason_code == "chunk_ready_default"
