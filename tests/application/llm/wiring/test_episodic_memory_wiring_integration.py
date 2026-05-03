"""create_llm_agent_wiring によるエピソードストア共有（保存側・受動想起側）の結合検証。"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)


def _deps_with_profile(player_id: int = 1) -> dict:
    """最小依存＋実プロフィール（prompt build が通る）"""
    uow_factory = MagicMock(spec=UnitOfWorkFactory)
    uow_factory.create.return_value = MagicMock()
    uow_factory.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow_factory.create.return_value.__exit__ = MagicMock(return_value=False)
    world_query = MagicMock(spec=WorldQueryService)
    world_query.get_player_current_state = MagicMock(return_value=None)
    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()

    data_store = InMemoryDataStore()
    data_store.clear_all()
    profile_repo: PlayerProfileRepository = InMemoryPlayerProfileRepository(data_store, None)
    profile = PlayerProfileAggregate.create(
        PlayerId(player_id), PlayerName("WiringRecall"), control_type=ControlType.LLM
    )
    profile_repo.save(profile)

    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": world_query,
        "movement_service": movement,
        "player_profile_repository": profile_repo,
        "unit_of_work_factory": uow_factory,
    }


def _minimal_episode(*, player_id: int, recall_text: str) -> SubjectiveEpisode:
    place_c = EpisodicCue(
        axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
    )
    return SubjectiveEpisode(
        episode_id="ep-wiring-int",
        player_id=player_id,
        occurred_at=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-wiring",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="noop_tool"),
        who=("w",),
        what="what",
        why=None,
        observed="obs",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(place_c,),
        recall_text=recall_text,
    )


class TestEpisodicMemoryWiringIntegration:
    """オーケストレータと DefaultPromptBuilder が同一 IEpisodicEpisodeStore を参照すること"""

    def test_wiring_exposes_shared_store_matching_orchestrator(self) -> None:
        """返却 episodic_episode_store が、オーケストレータ内部のストアと同一インスタンス。"""
        result = create_llm_agent_wiring(**_deps_with_profile())
        turn_runner = result.llm_turn_trigger._turn_runner  # noqa: SLF001
        orch = turn_runner._orchestrator  # noqa: SLF001
        assert result.episodic_episode_store is not None
        assert orch._episodic_episode_store is result.episodic_episode_store  # noqa: SLF001

    def test_prompt_builder_recalls_from_same_store_instance(self) -> None:
        """
        wiring が返すストアへ put したエピソードの recall_text が、
        同一 wiring の prompt_builder.build 経由で user コンテキストに載る（時間軸で取得）。
        """
        result = create_llm_agent_wiring(**_deps_with_profile(player_id=1))
        store = result.episodic_episode_store
        assert store is not None
        recall_phrase = "wiring_shared_store_recall_smoke"
        store.put(_minimal_episode(player_id=1, recall_text=recall_phrase))

        turn_runner = result.llm_turn_trigger._turn_runner  # noqa: SLF001
        orch = turn_runner._orchestrator  # noqa: SLF001
        prompt_builder = orch._prompt_builder  # noqa: SLF001

        out = prompt_builder.build(PlayerId(1))
        user_content = out["messages"][1]["content"]
        assert "## 関連する記憶" in user_content
        assert recall_phrase in user_content.split("## 関連する記憶", 1)[1]
        assert out["current_beliefs_snapshot"] == recall_phrase

    def test_injected_store_is_shared(self) -> None:
        """
        episodic_episode_store を明示注入した場合もオーケスト
        レータ・受動想起が同一ストアを参照し、build で recall できる。
        """
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )

        custom = InMemorySubjectiveEpisodeStore()
        base = _deps_with_profile()
        result = create_llm_agent_wiring(**base, episodic_episode_store=custom)
        assert result.episodic_episode_store is custom
        turn_runner = result.llm_turn_trigger._turn_runner  # noqa: SLF001
        orch = turn_runner._orchestrator  # noqa: SLF001
        assert orch._episodic_episode_store is custom  # noqa: SLF001

        recall_phrase = "injected_store_recall"
        custom.put(_minimal_episode(player_id=1, recall_text=recall_phrase))
        out = orch._prompt_builder.build(PlayerId(1))  # noqa: SLF001
        user_content = out["messages"][1]["content"]
        assert "## 関連する記憶" in user_content
        assert recall_phrase in user_content.split("## 関連する記憶", 1)[1]
