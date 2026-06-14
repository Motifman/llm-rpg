"""create_llm_agent_wiring と create_spot_graph_wiring の共有ビルダー群。

Issue #227 後続: 両 factory で完全重複していた 4 ブロックを抽出した:

1. effective_view_distance の env / argument 解決
2. EpisodicPromotionFrontier + memory_link_bundle + semantic_promotion の構築
3. recall_buffer / reinterpretation_coord / episodic_coord の構築
4. game_time_label_provider クロージャ生成 (action_result の時刻ラベル用)

呼び出し側のロジックを薄くし、両 factory の挙動が drift しないことを保証する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import WorldId

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.prompt_builder import (
    DEFAULT_RECENT_ACTIONS_LIMIT,
    DEFAULT_RECENT_OBSERVATIONS_LIMIT,
)
from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)
from ai_rpg_world.application.llm.wiring.episodic_memory_link_bundle import (
    EpisodicMemoryLinkBundle,
    build_episodic_memory_link_bundle,
    default_link_and_semantic_stores_for_episode_store,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)


_ENV_LLM_VIEW_DISTANCE = "LLM_VIEW_DISTANCE"
_DEFAULT_LLM_VIEW_DISTANCE = 5


def resolve_effective_view_distance(llm_view_distance: Optional[int]) -> int:
    """tile-map view distance の解決。

    引数 → 環境変数 LLM_VIEW_DISTANCE → default の順で解決し、負値や
    ValueError は default にフォールバックする。
    """
    if llm_view_distance is not None:
        return llm_view_distance
    raw = (os.environ.get(_ENV_LLM_VIEW_DISTANCE) or "").strip()
    if not raw:
        return _DEFAULT_LLM_VIEW_DISTANCE
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_LLM_VIEW_DISTANCE
    return value if value >= 0 else _DEFAULT_LLM_VIEW_DISTANCE


@dataclass(frozen=True)
class EpisodicMemoryStack:
    """episodic memory の中核コンポーネント束。

    shared_episode_store: 全 coordinator が共有する episode store
    semantic_memory_store: semantic promotion 先
    promotion_frontier: promotion 状態
    mem_bundle: link service / passive recall などのバンドル
    episodic_semantic_promotion: semantic cluster promotion service
    """

    shared_episode_store: EpisodicEpisodeRepository
    semantic_memory_store: Any
    promotion_frontier: EpisodicPromotionFrontier
    mem_bundle: EpisodicMemoryLinkBundle
    episodic_semantic_promotion: EpisodicSemanticClusterPromotionService


def build_episodic_memory_stack(
    episodic_episode_store: Optional[EpisodicEpisodeRepository],
    *,
    semantic_gist_service: Optional[Any] = None,
    semantic_persona_resolver: Optional[Any] = None,
    being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
    default_world_id: Optional["WorldId"] = None,
) -> EpisodicMemoryStack:
    """共有 episode store と link / semantic / promotion を組み立てる。

    create_llm_agent_wiring と create_spot_graph_wiring で完全に同じロジック
    だった 5 連鎖を 1 か所に集約する。

    Phase 1b (semantic LLM gist):
    - ``semantic_gist_service`` を渡すと cluster 昇格時に LLM gist を試みる
      (失敗時は決定論 gist にフォールバック)。default の None なら従来の
      決定論 gist のみ
    - ``semantic_persona_resolver`` は ``Callable[[int], tuple[str, str]]``。
      LLM gist の prompt に persona を載せるために必要。gist service を
      渡したら基本的に併せて渡す
    """
    shared_episode_store = resolve_default_episodic_episode_store(episodic_episode_store)
    link_store, semantic_memory_store = default_link_and_semantic_stores_for_episode_store(
        shared_episode_store
    )
    promotion_frontier = EpisodicPromotionFrontier()
    mem_bundle = build_episodic_memory_link_bundle(
        shared_episode_store,
        link_store=link_store,
        promotion_frontier=promotion_frontier,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    episodic_semantic_promotion = EpisodicSemanticClusterPromotionService(
        episode_store=shared_episode_store,
        link_store=mem_bundle.link_store,
        semantic_store=semantic_memory_store,
        promotion_frontier=promotion_frontier,
        gist_service=semantic_gist_service,
        persona_resolver=semantic_persona_resolver,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    return EpisodicMemoryStack(
        shared_episode_store=shared_episode_store,
        semantic_memory_store=semantic_memory_store,
        promotion_frontier=promotion_frontier,
        mem_bundle=mem_bundle,
        episodic_semantic_promotion=episodic_semantic_promotion,
    )


@dataclass(frozen=True)
class EpisodicCoordinatorStack:
    """recall buffer / reinterpretation / chunk coordinator の束。

    prompt_recall_buffer: prompt 用 (reinterpretation または explicit 指定時のみ非 None)
    reinterpretation_journal: 再解釈 journal
    reinterpretation_coord: 再解釈 coordinator
    episodic_coord: チャンク coordinator
    """

    prompt_recall_buffer: Optional[EpisodicRecallBufferRepository]
    reinterpretation_journal: EpisodicReinterpretationJournalRepository
    reinterpretation_coord: EpisodicReinterpretationCoordinator
    episodic_coord: EpisodicChunkCoordinator


def build_episodic_coordinator_stack(
    *,
    shared_episode_store: EpisodicEpisodeRepository,
    mem_bundle: EpisodicMemoryLinkBundle,
    buffer: IObservationContextBuffer,
    sliding_window: ISlidingWindowMemory,
    action_result_store: IActionResultStore,
    persona_block_provider: Any,
    recall_buffer: EpisodicRecallBufferRepository,
    reinterpretation_journal: EpisodicReinterpretationJournalRepository,
    episodic_recall_buffer_store_override: Optional[EpisodicRecallBufferRepository],
    chunk_episode_draft_builder: Optional[ChunkEpisodeDraftBuilder],
    chunk_subjective_service: Any,
    reinterpretation_completion: Optional[IEpisodicReinterpretationCompletionPort],
    episodic_chunk_coordinator_override: Optional[EpisodicChunkCoordinator],
) -> EpisodicCoordinatorStack:
    """recall_buffer / reinterpretation_coord / episodic_coord の組み立てを集約する。

    create_llm_agent_wiring と create_spot_graph_wiring で 40 行重複していた
    ブロックを抽出。recall_buffer / reinterpretation_journal の解決は呼び出し側
    (`__init__.py` の `_resolve_default_episodic_reinterpretation_stores`) で
    済ませてから渡す (循環 import 回避)。
    """
    chunk_builder = (
        chunk_episode_draft_builder
        if chunk_episode_draft_builder is not None
        else ChunkEpisodeDraftBuilder()
    )
    reinterpretation_coord = EpisodicReinterpretationCoordinator(
        episode_store=shared_episode_store,
        recall_buffer_store=recall_buffer,
        journal_store=reinterpretation_journal,
        completion=reinterpretation_completion,
    )
    # prompt 経路で recall buffer を覗くのは
    # (a) reinterpretation_completion が有効、または
    # (b) caller が明示的に store を渡している
    # ときのみ。それ以外は prompt builder には None を渡し、無駄な query を防ぐ。
    prompt_recall_buffer = (
        recall_buffer
        if reinterpretation_completion is not None
        or episodic_recall_buffer_store_override is not None
        else None
    )
    episodic_coord = episodic_chunk_coordinator_override or EpisodicChunkCoordinator(
        observation_buffer=buffer,
        sliding_window_memory=sliding_window,
        action_result_store=action_result_store,
        episodic_episode_store=shared_episode_store,
        chunk_episode_draft_builder=chunk_builder,
        recent_observations_limit=DEFAULT_RECENT_OBSERVATIONS_LIMIT,
        recent_actions_limit=DEFAULT_RECENT_ACTIONS_LIMIT,
        chunk_subjective_fields_service=chunk_subjective_service,
        persona_block_provider=persona_block_provider
        if chunk_subjective_service is not None
        else None,
        episodic_memory_link_service=mem_bundle.link_service,
    )
    return EpisodicCoordinatorStack(
        prompt_recall_buffer=prompt_recall_buffer,
        reinterpretation_journal=reinterpretation_journal,
        reinterpretation_coord=reinterpretation_coord,
        episodic_coord=episodic_coord,
    )


def build_game_time_label_provider(
    game_time_provider: Any,
    world_time_config_service: Any,
) -> Optional[Callable[[], Optional[str]]]:
    """action_result の時刻ラベル用 provider を組み立てる。

    Issue #188 改善: action_result に観測と同じ時刻ラベルを乗せる。
    game_time_provider と world_time_config_service が両方注入されていれば、
    tick を game_date_time に変換して display 用ラベルを返す。

    どちらかが None なら None を返す (= ラベルなしで orchestrator に渡される)。

    NOTE: Issue #227 後続のレビュー (MEDIUM-6) で、tile-map 版 create_llm_agent_wiring
    から本 provider が抜けていた潜在バグを発見したため、共通 helper にして両 factory で
    一貫して使うようにした。
    """
    if game_time_provider is None or world_time_config_service is None:
        return None

    from ai_rpg_world.domain.world.value_object.game_date_time import (
        game_date_time_from_tick,
    )

    def _build_game_time_label() -> Optional[str]:
        try:
            tick = game_time_provider.get_current_tick().value
            game_dt = game_date_time_from_tick(
                tick,
                world_time_config_service.get_ticks_per_day(),
                world_time_config_service.get_days_per_month(),
                world_time_config_service.get_months_per_year(),
            )
            return game_dt.format_for_display()
        except Exception:
            return None

    return _build_game_time_label
