"""Phase 3 Step 3d-2: reinterpretation caller dual-path テスト。

``EpisodicReinterpretationCoordinator`` が Resolver 注入時に
``*_by_being`` API 経由で recall_buffer / journal を読み書きすることを
確認する。
"""

from __future__ import annotations

# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p1")

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.application.llm._reinterpretation_being_test_helpers import (
    make_reinterpretation_being_setup,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _ep(episode_id: str = "e1", player_id: int = 1) -> SubjectiveEpisode:
    cue = EpisodicCue(
        axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=_NOW,
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("evt",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted="i",
        cues=(cue,),
        recall_text="raw recall",
        recall_count=0,
        last_recalled_at=None,
    )


def _obs(
    *, recall_id: str, episode_id: str = "e1", player_id: int = 1
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=player_id,
        episode_id=episode_id,
        recalled_at=_NOW,
        source_axes=("temporal",),
        current_state_snapshot="s",
        recent_events_snapshot="r",
        persona_snapshot="p",
        situation_cues=("c",),
        turn_index=1,
    )


class _StubCompletion(IEpisodicReinterpretationCompletionPort):
    """指定の JSON dict を返す stub completion。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def complete_episodic_reinterpretation_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._payload


class TestCoordinatorDualPath:
    """``EpisodicReinterpretationCoordinator.flush_player`` の経路切り替え。"""

    def test_resolver_注入_時は_being_id_経路で_recall_buffer_を_読む(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(1)
        # Phase 3 Step 3e-2: Coordinator が being_id 経由で episode を引く
        episodes.put_by_being(being_id, _ep("e1"))
        # being_id 経路に observation を書く
        setup.recall_buffer.append_by_being(being_id, _obs(recall_id="r1"))
        completion = _StubCompletion(
            {
                "episode_updates": [
                    {
                        "episode_id": "e1",
                        "current_interpretation": "reinterp text",
                        "current_recall_text": "recall text",
                    }
                ]
            }
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=setup.recall_buffer,
            journal_store=setup.journal,
            completion=completion,
            turn_interval=1,
            batch_size=4,
            max_contexts_per_episode=3,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        processed = coord.flush_player(PlayerId(1))
        assert processed == 1
        # journal 側にも being_id 経由で entry が書かれる
        active = setup.journal.get_active_by_being(being_id, "e1")
        assert active is not None
        assert active.current_interpretation == "reinterp text"
        # being_id 経路の recall_buffer は 0 件に
        assert setup.recall_buffer.pending_count_by_being(being_id) == 0

    def test_resolver_未注入_時は_silent_no_op(self) -> None:
        """Phase 3 Step 3d-3: legacy 撤去後、Resolver 未注入は silent skip。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(1)
        episodes.put_by_being(being_id, _ep("e1"))
        # being_id 経路に observation を書いておく
        setup.recall_buffer.append_by_being(being_id, _obs(recall_id="r1"))
        completion = _StubCompletion(
            {
                "episode_updates": [
                    {
                        "episode_id": "e1",
                        "current_interpretation": "reinterp",
                        "current_recall_text": "recall",
                    }
                ]
            }
        )
        # Resolver 注入なしで構築 (= legacy 経路は撤去済)
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=setup.recall_buffer,
            journal_store=setup.journal,
            completion=completion,
            turn_interval=1,
            batch_size=4,
            max_contexts_per_episode=3,
        )
        processed = coord.flush_player(PlayerId(1))
        # being_id を解決できないため silent no-op
        assert processed == 0
        # recall_buffer は手付かず (= 次回 turn で再試行できる)
        assert setup.recall_buffer.pending_count_by_being(being_id) == 1
        # journal にも書かれない
        assert setup.journal.get_active_by_being(being_id, "e1") is None


class TestCoordinatorTypeGuard:
    """constructor の型ガード。"""

    def test_resolver_型違反は_TypeError(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        with pytest.raises(TypeError, match="being_attachment_resolver"):
            EpisodicReinterpretationCoordinator(
                episode_store=episodes,
                recall_buffer_store=setup.recall_buffer,
                journal_store=setup.journal,
                completion=None,
                being_attachment_resolver="not-resolver",  # type: ignore[arg-type]
            )

    def test_world_id_型違反は_TypeError(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        with pytest.raises(TypeError, match="default_world_id"):
            EpisodicReinterpretationCoordinator(
                episode_store=episodes,
                recall_buffer_store=setup.recall_buffer,
                journal_store=setup.journal,
                completion=None,
                default_world_id="not-world-id",  # type: ignore[arg-type]
            )


class TestPromptBuilderRecallBufferDualPath:
    """``DefaultPromptBuilder._run_passive_recall`` が being_id 経路で
    recall buffer に書くことを統合テストする。

    DefaultPromptBuilder 全体は複雑な依存を要求するため、本テストは
    ``_join_passive_recall_texts`` ヘルパー単体で journal の経路切り替えを
    確認する (= 主要ロジックの非対称はここで担保し、append 経路は
    integration test に委ねる方針)。
    """

    def test_being_id_を_渡すと_journal_を_being_id_経路で_読む(self) -> None:
        from ai_rpg_world.application.llm.services.prompt_builder import (
            _join_passive_recall_texts,
        )
        from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
            EpisodicPassiveRecallCandidate,
        )
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
            EpisodicReinterpretationEntry,
        )
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
            EpisodicReinterpretationStatus,
        )

        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(1)
        # being_id 経路に active entry を書く
        setup.journal.put_active_by_being(
            being_id,
            EpisodicReinterpretationEntry(
                entry_id="ent-1",
                player_id=1,
                episode_id="e1",
                created_at=_NOW,
                turn_index=1,
                current_interpretation="reinterp",
                current_recall_text="REINTERPRETED",
                source_recall_ids=("r-1",),
                status=EpisodicReinterpretationStatus.ACTIVE,
                superseded_at=None,
            ),
        )
        cand = EpisodicPassiveRecallCandidate(
            episode=_ep("e1"),
            source_axes=("temporal",),
        )
        result = _join_passive_recall_texts(
            1,
            (cand,),
            setup.journal,
            being_id=being_id,
        )
        assert result == "REINTERPRETED"

    def test_append_recall_observation_は_being_id_あれば_書き_None_なら_skip(self) -> None:
        """Phase 3 Step 3d-3: legacy 撤去後、Being 未解決時は silent skip。"""
        # being_id 注入時 → append_by_being が呼ばれる
        store_new = MagicMock()
        builder_with_being = MagicMock()
        builder_with_being._episodic_recall_buffer_store = store_new
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )

        being_id_obj = MagicMock(name="BeingId")
        observation_obj = MagicMock(name="EpisodicRecallObservation")
        DefaultPromptBuilder._append_recall_observation(
            builder_with_being, being_id_obj, observation_obj
        )
        store_new.append_by_being.assert_called_once_with(being_id_obj, observation_obj)

        # being_id 未指定 → silent skip (= 何も書かれない)
        store_no_buffer = MagicMock()
        builder_no_being = MagicMock()
        builder_no_being._episodic_recall_buffer_store = store_no_buffer
        DefaultPromptBuilder._append_recall_observation(
            builder_no_being, None, observation_obj
        )
        store_no_buffer.append_by_being.assert_not_called()

    def test_being_id_未指定なら_生_recall_text_に_縮退(self) -> None:
        """Phase 3 Step 3d-3: legacy journal lookup 撤去後、Being 未解決時は
        journal をスキップして生の ``recall_text`` を使う graceful fallback。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            _join_passive_recall_texts,
        )
        from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
            EpisodicPassiveRecallCandidate,
        )

        setup = make_reinterpretation_being_setup()
        cand = EpisodicPassiveRecallCandidate(
            episode=_ep("e1"),
            source_axes=("temporal",),
        )
        result = _join_passive_recall_texts(
            1,
            (cand,),
            setup.journal,
            being_id=None,
        )
        # being_id 未指定 → 生 recall_text を返す
        assert result == "raw recall"
